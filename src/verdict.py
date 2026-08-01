"""Turns a calculation into one of three user-facing conclusions.

The distinction this module exists to enforce: **some findings depend on the
benchmark and some do not.**

- The Decree 43 tier table needs the market average. Ours is an indicative
  estimate, not RERA's official building-level index, so a tier-based finding
  can only ever be "appears to exceed" — never "is unlawful".
- Article 9's two-year freeze and Article 14's notice period are pure date
  arithmetic over dates printed in the contract. No benchmark is involved, so
  those findings can be stated plainly.

Collapsing the two would either overstate the tier finding or needlessly hedge
the date findings. Both are failures, in opposite directions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    WITHIN_RANGE = "within_range"
    POSSIBLY_ABOVE = "possibly_above"
    VERIFICATION_REQUIRED = "verification_required"
    UNDETERMINED = "undetermined"


TONES = {
    Outcome.WITHIN_RANGE: "success",
    Outcome.POSSIBLY_ABOVE: "warning",
    Outcome.VERIFICATION_REQUIRED: "neutral",
    Outcome.UNDETERMINED: "muted",
}

STATUS_LABELS = {
    Outcome.WITHIN_RANGE: "Within permitted range",
    Outcome.POSSIBLY_ABOVE: "Potentially above permitted range",
    Outcome.VERIFICATION_REQUIRED: "Official verification required",
    Outcome.UNDETERMINED: "Unable to determine",
}


@dataclass
class Verdict:
    outcome: Outcome
    headline: str
    explanation: str
    tone: str
    benchmark_is_official: bool = False
    data_source: str = "Not available"
    last_checked: str = "Not available"
    evidence_note: str = ""
    definitive_findings: list[str] = field(default_factory=list)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.outcome]


def classify(calculation: dict, benchmark: dict) -> Verdict:
    """Decide the headline conclusion from the calculation payload."""
    source_kind = (benchmark or {}).get("source_kind", "")
    confidence = (benchmark or {}).get("confidence", "low")
    official = source_kind == "dld_registered_contracts" and confidence == "high"
    data_source = _describe_source(benchmark, official)
    last_checked = (benchmark or {}).get("snapshot_date") or "Not available"

    if not calculation or not calculation.get("determinable"):
        return Verdict(
            outcome=Outcome.UNDETERMINED,
            headline="We could not complete this assessment",
            explanation=(
                calculation.get("reason")
                or "Key details could not be established from the document provided."
            ),
            tone=TONES[Outcome.UNDETERMINED],
            benchmark_is_official=official,
            data_source=data_source,
            last_checked=last_checked,
        )

    definitive = _definitive_findings(calculation)

    # Article 9 does not depend on the benchmark, so it can be stated plainly.
    if calculation.get("article_9_blocks_increase"):
        freeze_until = calculation.get("two_year_freeze_until") or "the two-year point"
        return Verdict(
            outcome=Outcome.POSSIBLY_ABOVE,
            headline="No increase is permitted during the first two years",
            explanation=(
                "Article 9 of Law 26/2007 prevents any rent increase until "
                f"{freeze_until}, counted from when the tenancy first began. This "
                "does not depend on market data, so it applies regardless of the "
                "benchmark."
            ),
            tone="risk",
            benchmark_is_official=official,
            data_source=data_source,
            last_checked=last_checked,
            evidence_note="Based on dates in your contract, not on market data.",
            definitive_findings=definitive,
        )

    proposed_pct = calculation.get("proposed_increase_pct")
    excess = calculation.get("excess_over_lawful_aed")
    max_low, max_high = (calculation.get("max_increase_pct") or [None, None])[:2]

    # Nothing requested: report the estimated headroom, don't invent a dispute.
    if proposed_pct is None:
        return Verdict(
            outcome=Outcome.VERIFICATION_REQUIRED,
            headline="No proposed increase was found in the document",
            explanation=(
                "We could not find a requested rent for renewal, so there is nothing "
                "to compare. The estimated permitted range is shown below for "
                f"reference{_range_phrase(max_low, max_high)}."
            ),
            tone=TONES[Outcome.VERIFICATION_REQUIRED],
            benchmark_is_official=official,
            data_source=data_source,
            last_checked=last_checked,
            definitive_findings=definitive,
        )

    if excess:
        headline = "The requested increase appears to exceed the permitted range"
        explanation = (
            f"The requested increase of {_pct(proposed_pct)} appears to exceed the "
            f"estimated permitted range{_range_phrase(max_low, max_high)}. "
        )
        explanation += (
            "This is based on the official registered-contract dataset."
            if official
            else (
                "This estimate uses an indicative benchmark rather than the official "
                "rental index. Confirm the property through the official index "
                "before relying on this result."
            )
        )
        return Verdict(
            outcome=Outcome.POSSIBLY_ABOVE,
            headline=headline,
            explanation=explanation,
            tone="warning" if not official else "risk",
            benchmark_is_official=official,
            data_source=data_source,
            last_checked=last_checked,
            evidence_note=(
                "" if official else "Benchmark is indicative; official confirmation needed."
            ),
            definitive_findings=definitive,
        )

    return Verdict(
        outcome=Outcome.WITHIN_RANGE,
        headline="The requested increase appears to be within the permitted range",
        explanation=(
            f"The requested increase of {_pct(proposed_pct)} falls within the "
            f"estimated permitted range{_range_phrase(max_low, max_high)}. "
            + (
                ""
                if official
                else "The benchmark used is indicative, so confirm through the "
                "official rental index before treating this as settled."
            )
        ),
        tone=TONES[Outcome.WITHIN_RANGE],
        benchmark_is_official=official,
        data_source=data_source,
        last_checked=last_checked,
        definitive_findings=definitive,
    )


def _definitive_findings(calculation: dict) -> list[str]:
    """Findings that stand independently of the benchmark."""
    findings: list[str] = []

    notice = calculation.get("notice_check") or {}
    if notice.get("determinable") and notice.get("compliant") is False:
        days = notice.get("days_given")
        findings.append(
            f"Notice was served {days} days before expiry, short of the 90 days "
            "required to change any term of the contract."
            if days is not None
            else "The notice period requirement does not appear to have been met."
        )

    if calculation.get("article_9_blocks_increase"):
        findings.append(
            "The tenancy is within its first two years, during which no increase "
            "is permitted."
        )
    return findings


def _describe_source(benchmark: dict, official: bool) -> str:
    if not benchmark or not benchmark.get("found", True):
        return "No benchmark available"
    if official:
        return "DLD registered rental contracts"
    return "Indicative market estimate"


def _range_phrase(low, high) -> str:
    if low is None:
        return ""
    if high is None or low == high:
        return f" of {low}%"
    return f" of {low}%–{high}%"


def _pct(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "the requested amount"
    return f"{number:.0f}%" if number == int(number) else f"{number:.1f}%"
