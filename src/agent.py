"""The audit agent: a hand-written tool-use loop over Claude Opus 5.

Hand-written rather than using the SDK's tool runner, for one reason: every
intermediate step has to be renderable. The loop yields a Step for each thinking
block, tool call, and tool result as it happens, so the UI can show the agent
working instead of a spinner followed by an answer.

Cost ceilings are enforced here and fail loudly. An agent loop that quietly
retries is how you wake up to an empty API budget.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

import anthropic

from src import config, legal, tools

# Opus 5 list price, US dollars per million tokens.
COST_PER_MTOK_INPUT = 5.00
COST_PER_MTOK_OUTPUT = 25.00
COST_PER_MTOK_CACHE_READ = 0.50


class StepKind(str, Enum):
    PLAN = "plan"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TEXT = "text"
    DONE = "done"
    ERROR = "error"
    ABORTED = "aborted"
    REFUSED = "refused"


@dataclass
class Step:
    kind: StepKind
    title: str = ""
    body: str = ""
    tool_name: str = ""
    payload: dict = field(default_factory=dict)
    display: dict = field(default_factory=dict)
    is_error: bool = False
    iteration: int = 0


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    iterations: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * COST_PER_MTOK_INPUT
            + self.output_tokens / 1_000_000 * COST_PER_MTOK_OUTPUT
            + self.cache_read_tokens / 1_000_000 * COST_PER_MTOK_CACHE_READ
        )


def _corpus_for_prompt() -> str:
    """Render the verified corpus as the only citable authority."""
    corpus = legal.load_corpus()
    lines = [
        "These are the ONLY provisions you may cite. Each is identified by an id.",
        "Citing an id not in this list is rejected by the tools.",
        "",
    ]
    tier = corpus["rent_increase_tiers"]
    lines.append(
        f"Rent increase tiers — {tier['instrument']}, Article {tier['article']}: "
        f"{tier['basis']}"
    )
    for band in tier["tiers"]:
        ceiling = band["max_pct_below"]
        span = f"{band['min_pct_below']}–{ceiling}% below" if ceiling else "more than 40% below"
        lines.append(f"  · {span} → maximum increase {band['max_increase_pct']}%")
    lines.append("")

    for item in corpus["provisions"]:
        kind = "QUOTE" if "quote" in item else "SUMMARY (not verbatim — never quote it)"
        text = item.get("quote") or item.get("summary")
        lines += [
            f"id: {item['id']}",
            f"  {item['instrument']}, Article {item['article']} — {item['short_title']}",
            f"  [{kind}] {text}",
        ]
        if item.get("tenant_use"):
            lines.append(f"  Relevance: {item['tenant_use']}")
        lines.append("")
    return "\n".join(lines)


SYSTEM_PROMPT = """You audit Dubai residential tenancy contracts for tenants. \
A tenant has uploaded their contract because their landlord wants to raise the \
rent, and they need to know whether that is lawful and what to say about it.

# How you work

Call the tools in this order, once each: parse_contract, lookup_benchmark, \
calculate_legal_max, check_clauses, generate_talking_points. Read each result \
before deciding the next call.

# Rules you do not break

**You do no arithmetic.** calculate_legal_max performs every calculation. Never \
compute a percentage, a gap, or a rent ceiling yourself, and never state a \
figure that a tool did not return to you. If you find yourself about to do \
mental maths about money, call the tool instead.

**You do not invent law.** You may cite only the provision ids listed below. \
The tools verify every id and reject unknown ones. If a situation is not covered \
by a provision in that list, say plainly that you cannot establish the position \
rather than describing a rule from memory. There is no penalty for saying "I \
can't determine this" and considerable harm in guessing about someone's housing.

**You report gaps.** If a field is unreadable, an area is not in the dataset, or \
a date is missing, name it in cannot_determine. A stated limitation is useful; a \
confident wrong answer about rent is not.

**You distinguish quotes from summaries.** Provisions marked SUMMARY are \
paraphrases. Never present them inside quotation marks.

**You do not over-flag.** Some one-sided-looking clauses are the statutory \
default — tenant liability for government fees is lawful under Article 22, for \
instance. Record those as 'lawful' so the tenant can see they were reviewed.

**Benchmark confidence matters.** If lookup_benchmark reports low confidence, the \
permitted increase is a range rather than a single figure, and you must say the \
tenant should confirm against the official RERA Smart Rental Index before acting.

# Tone

Write for a worried tenant, not a lawyer. Short sentences. No legalese unless you \
immediately explain it. Lead with the answer, then the reasoning. This is guidance, \
not legal advice, and you should not pretend otherwise.

# The provisions you may cite

{corpus}"""


class BudgetExceeded(RuntimeError):
    """Raised when a run exceeds its token or iteration ceiling."""


def run(
    pdf_bytes: bytes,
    filename: str = "contract.pdf",
    today: date | None = None,
    api_key: str | None = None,
) -> Iterator[Step]:
    """Audit one contract, yielding a Step per observable event.

    Raises BudgetExceeded rather than silently continuing past a ceiling.
    """
    key = api_key or config.anthropic_api_key()
    if not key:
        yield Step(
            kind=StepKind.ERROR,
            title="No API key configured",
            body="Set ANTHROPIC_API_KEY in Streamlit secrets or the environment.",
            is_error=True,
        )
        return

    client = anthropic.Anthropic(api_key=key)
    usage = Usage()
    max_tokens_budget = config.max_tokens_per_run()
    max_iterations = config.max_agent_iterations()
    assessment_date = (today or date.today()).isoformat()

    system = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT.format(corpus=_corpus_for_prompt()),
            # Stable across every run, so cache it: the corpus is most of the
            # prompt and re-paying for it each audit is pure waste.
            "cache_control": {"type": "ephemeral"},
        }
    ]

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(pdf_bytes).decode(),
                    },
                    "title": filename,
                },
                {
                    "type": "text",
                    "text": (
                        f"Today's date is {assessment_date}. Audit this tenancy "
                        "contract. Work through the five tools in order, then give "
                        "the tenant their verdict and what to say."
                    ),
                },
            ],
        }
    ]

    yield Step(
        kind=StepKind.PLAN,
        title="Plan",
        body=(
            "Read the contract → find the market benchmark → apply Decree 43/2013, "
            "Article 9 and the notice rule → check clauses against the verified "
            "corpus → draft negotiating points."
        ),
    )

    for iteration in range(1, max_iterations + 1):
        usage.iterations = iteration

        if usage.total_tokens > max_tokens_budget:
            yield Step(
                kind=StepKind.ABORTED,
                title="Token ceiling reached",
                body=(
                    f"This run used {usage.total_tokens:,} tokens against a ceiling "
                    f"of {max_tokens_budget:,} and was stopped. Nothing was retried."
                ),
                is_error=True,
            )
            return

        try:
            response = client.messages.create(
                model=config.MODEL,
                max_tokens=16_000,
                system=system,
                messages=messages,
                tools=tools.TOOL_SCHEMAS,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": "high"},
            )
        except anthropic.APIStatusError as exc:
            yield Step(
                kind=StepKind.ERROR,
                title=f"API error {exc.status_code}",
                body=str(exc.message),
                is_error=True,
            )
            return
        except anthropic.APIConnectionError:
            yield Step(
                kind=StepKind.ERROR,
                title="Connection failed",
                body="Could not reach the API. Check the network and try again.",
                is_error=True,
            )
            return

        if response.usage:
            usage.input_tokens += response.usage.input_tokens or 0
            usage.output_tokens += response.usage.output_tokens or 0
            usage.cache_read_tokens += getattr(response.usage, "cache_read_input_tokens", 0) or 0

        # Opus 5 can decline via a successful response, so check before reading
        # content — indexing content[0] on a refusal would crash.
        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            yield Step(
                kind=StepKind.REFUSED,
                title="The model declined this request",
                body=(
                    "The safety classifiers declined to process this document"
                    + (f" (category: {detail.category})" if detail and detail.category else "")
                    + ". If this is a genuine tenancy contract, please report it."
                ),
                is_error=True,
            )
            return

        for block in response.content:
            if block.type == "thinking" and getattr(block, "thinking", ""):
                yield Step(
                    kind=StepKind.THINKING,
                    title="Reasoning",
                    body=block.thinking,
                    iteration=iteration,
                )
            elif block.type == "text" and block.text.strip():
                yield Step(
                    kind=StepKind.TEXT,
                    body=block.text,
                    iteration=iteration,
                )

        if response.stop_reason != "tool_use":
            yield Step(
                kind=StepKind.DONE,
                title="Audit complete",
                payload={
                    "iterations": usage.iterations,
                    "total_tokens": usage.total_tokens,
                    "estimated_cost_usd": round(usage.estimated_cost_usd, 4),
                },
            )
            return

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            yield Step(
                kind=StepKind.TOOL_CALL,
                title=block.name,
                tool_name=block.name,
                payload=dict(block.input),
                iteration=iteration,
            )

            result = tools.execute(block.name, dict(block.input))

            yield Step(
                kind=StepKind.TOOL_RESULT,
                title=block.name,
                tool_name=block.name,
                payload=result.payload,
                display=result.display,
                is_error=result.is_error,
                iteration=iteration,
            )

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _as_text(result.payload),
                    "is_error": result.is_error,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    yield Step(
        kind=StepKind.ABORTED,
        title="Iteration ceiling reached",
        body=(
            f"The agent used all {max_iterations} permitted steps without "
            "finishing. Stopped rather than looping further."
        ),
        is_error=True,
    )


def _as_text(payload: dict) -> str:
    import json

    return json.dumps(payload, indent=2, default=str)
