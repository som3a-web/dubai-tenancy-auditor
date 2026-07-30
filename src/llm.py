"""Provider backends for the audit agent.

The agent loop is provider-agnostic: it drives a Backend and renders Steps. Two
backends exist — Anthropic and Google Gemini — because the free Gemini tier lets
this run without prepaid credit, while Anthropic remains available if credit is
added later. Whichever key is present is used; if both are, PROVIDER decides.

Only the conversation plumbing lives here. Tool execution, the legal engine and
the UI are shared and untouched by the choice of provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# --------------------------------------------------------------------------
# Normalised turn
# --------------------------------------------------------------------------


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Turn:
    """One model response, normalised across providers."""

    thinking: list[str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    wants_tools: bool = False
    refused: bool = False
    refusal_detail: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass
class ToolOutcome:
    call: ToolCall
    payload: dict
    is_error: bool


class Backend(Protocol):
    name: str
    model: str

    def begin(self, system: str, pdf_bytes: bytes, filename: str, prompt: str) -> None: ...
    def next_turn(self) -> Turn: ...
    def submit_tool_results(self, outcomes: list[ToolOutcome]) -> None: ...


# --------------------------------------------------------------------------
# Schema translation
# --------------------------------------------------------------------------


def to_gemini_schema(schema: dict) -> dict:
    """Rewrite a JSON Schema so Gemini accepts it.

    The tool schemas use nullable unions like {"type": ["string", "null"]} to let
    the model report a field it genuinely could not read. Gemini's schema
    validator rejects type arrays, so collapse each union to its non-null type.
    Nothing is lost: those fields are already absent from `required`, so "omit
    it" still expresses "I could not read this".
    """
    if not isinstance(schema, dict):
        return schema

    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "type" and isinstance(value, list):
            concrete = [t for t in value if t != "null"]
            out["type"] = concrete[0] if concrete else "string"
        elif key in ("properties", "$defs") and isinstance(value, dict):
            out[key] = {k: to_gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out[key] = to_gemini_schema(value)
        elif isinstance(value, dict):
            out[key] = to_gemini_schema(value)
        elif isinstance(value, list) and key not in ("required", "enum"):
            out[key] = [to_gemini_schema(v) if isinstance(v, dict) else v for v in value]
        else:
            out[key] = value
    return out


# --------------------------------------------------------------------------
# Anthropic
# --------------------------------------------------------------------------


class AnthropicBackend:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, tool_schemas: list[dict]):
        import anthropic

        self._sdk = anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.tools = tool_schemas
        self.system: list[dict] = []
        self.messages: list[dict] = []

    def begin(self, system: str, pdf_bytes: bytes, filename: str, prompt: str) -> None:
        import base64

        self.system = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        self.messages = [
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
                    {"type": "text", "text": prompt},
                ],
            }
        ]

    def next_turn(self) -> Turn:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=16_000,
            system=self.system,
            messages=self.messages,
            tools=self.tools,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": "high"},
        )
        self._last = response

        turn = Turn()
        if response.usage:
            turn.input_tokens = response.usage.input_tokens or 0
            turn.output_tokens = response.usage.output_tokens or 0
            turn.cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            turn.refused = True
            turn.refusal_detail = getattr(detail, "category", "") or ""
            return turn

        for block in response.content:
            if block.type == "thinking" and getattr(block, "thinking", ""):
                turn.thinking.append(block.thinking)
            elif block.type == "text" and block.text.strip():
                turn.text.append(block.text)
            elif block.type == "tool_use":
                turn.tool_calls.append(ToolCall(block.id, block.name, dict(block.input)))

        turn.wants_tools = response.stop_reason == "tool_use"
        return turn

    def submit_tool_results(self, outcomes: list[ToolOutcome]) -> None:
        import json

        self.messages.append({"role": "assistant", "content": self._last.content})
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": o.call.id,
                        "content": json.dumps(o.payload, indent=2, default=str),
                        "is_error": o.is_error,
                    }
                    for o in outcomes
                ],
            }
        )


# --------------------------------------------------------------------------
# Google Gemini
# --------------------------------------------------------------------------


class GeminiBackend:
    name = "gemini"

    # Tried in order when the current model 404s or exhausts its daily quota.
    # Each entry has its OWN free-tier quota, so rotating multiplies the budget.
    FALLBACK_ORDER = (
        "gemini-flash-latest",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
        "gemini-2.0-flash",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-2.0-flash-lite",
    )

    def __init__(self, api_key: str, model: str, tool_schemas: list[dict]):
        from google import genai
        from google.genai import types

        self._types = types
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=schema["name"],
                    description=schema["description"],
                    parameters_json_schema=to_gemini_schema(schema["input_schema"]),
                )
                for schema in tool_schemas
            ]
        )
        self.system = ""
        self.contents: list[Any] = []
        self._call_index = 0
        self._tried_models: set[str] = set()

    def _callable_models(self) -> list[str]:
        try:
            return [
                m.name.removeprefix("models/")
                for m in self.client.models.list()
                if "generateContent"
                in (getattr(m, "supported_actions", None) or ["generateContent"])
            ]
        except Exception:
            return []

    def resolve_model(self) -> str:
        """Cheap pre-flight check that the configured model is at least listed.

        Deliberately weak: being listed does NOT mean an account can call it.
        Google retires specific versions for new accounts while leaving them in
        models.list(), so gemini-2.5-flash can appear here and still 404 on the
        first request. The real safety net is the 404 retry in next_turn().
        """
        available = self._callable_models()
        if not available or self.model in available:
            return self.model
        self.model = self._pick_fallback(available)
        return self.model

    @staticmethod
    def _pick_fallback(available: list[str]) -> str:
        """Choose the best Flash model from what the account can see.

        Aliases first — they track the current release and cannot go stale.
        """
        for alias in ("gemini-flash-latest", "gemini-3.6-flash", "gemini-3.5-flash"):
            if alias in available:
                return alias
        flash = [
            m
            for m in available
            if "flash" in m
            and not any(bad in m for bad in ("lite", "audio", "image", "tts", "live", "omni"))
        ]
        return (flash or available)[0]

    def _generate_with_fallback(self):
        """Call the model, rotating to a different one on 404 or quota exhaustion.

        The free tier's quota is *per model per day* (20 requests at the time of
        writing), and one audit costs roughly six. Rotating to another Flash model
        when one is exhausted multiplies the usable budget instead of failing the
        audit outright. A model can also be listed but not callable, which 404s
        on first use — same recovery.

        Each model is tried at most once per run so this cannot spin.
        """
        last_error: Exception | None = None

        for _ in range(len(self.FALLBACK_ORDER) + 1):
            self._tried_models.add(self.model)
            try:
                return self._generate()
            except Exception as exc:  # noqa: BLE001 - providers raise many shapes
                text = str(exc)
                recoverable = any(
                    marker in text
                    for marker in (
                        "NOT_FOUND", "404",           # listed but not callable
                        "RESOURCE_EXHAUSTED", "429",  # per-model daily quota
                        "UNAVAILABLE", "503",         # transient overload
                        "INTERNAL", "500",
                    )
                )
                if not recoverable:
                    raise
                last_error = exc
                replacement = self._next_untried_model()
                if replacement is None:
                    raise
                self.model = replacement

        if last_error:
            raise last_error
        raise RuntimeError("no model could be reached")

    def _next_untried_model(self) -> str | None:
        for candidate in self.FALLBACK_ORDER:
            if candidate not in self._tried_models:
                return candidate
        for candidate in self._callable_models():
            if candidate not in self._tried_models and "flash" in candidate:
                return candidate
        return None

    def _generate(self):
        types = self._types
        return self.client.models.generate_content(
            model=self.model,
            contents=self.contents,
            config=types.GenerateContentConfig(
                system_instruction=self.system,
                tools=[self.tool],
                # The loop drives tools itself so each call can be rendered.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                thinking_config=types.ThinkingConfig(include_thoughts=True),
                max_output_tokens=16_000,
            ),
        )

    def begin(self, system: str, pdf_bytes: bytes, filename: str, prompt: str) -> None:
        types = self._types
        self.system = system
        self.contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    types.Part.from_text(text=prompt),
                ],
            )
        ]

    def next_turn(self) -> Turn:
        response = self._generate_with_fallback()
        self._last = response

        turn = Turn()
        meta = getattr(response, "usage_metadata", None)
        if meta:
            turn.input_tokens = getattr(meta, "prompt_token_count", 0) or 0
            turn.output_tokens = getattr(meta, "candidates_token_count", 0) or 0
            turn.cache_read_tokens = getattr(meta, "cached_content_token_count", 0) or 0

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            turn.refused = True
            turn.refusal_detail = str(getattr(response, "prompt_feedback", "") or "no candidates")
            return turn

        candidate = candidates[0]
        if str(getattr(candidate, "finish_reason", "")).endswith("SAFETY"):
            turn.refused = True
            turn.refusal_detail = "safety"
            return turn

        for part in (getattr(candidate.content, "parts", None) or []):
            if getattr(part, "thought", False) and getattr(part, "text", None):
                turn.thinking.append(part.text)
            elif getattr(part, "function_call", None):
                call = part.function_call
                self._call_index += 1
                turn.tool_calls.append(
                    ToolCall(
                        id=getattr(call, "id", None) or f"{call.name}-{self._call_index}",
                        name=call.name,
                        args=dict(call.args or {}),
                    )
                )
            elif getattr(part, "text", None) and part.text.strip():
                turn.text.append(part.text)

        turn.wants_tools = bool(turn.tool_calls)
        return turn

    def submit_tool_results(self, outcomes: list[ToolOutcome]) -> None:
        types = self._types
        self.contents.append(self._last.candidates[0].content)
        self.contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=o.call.name,
                        response=o.payload if isinstance(o.payload, dict) else {"result": o.payload},
                    )
                    for o in outcomes
                ],
            )
        )


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------


def build_backend(tool_schemas: list[dict]) -> tuple[Backend | None, str]:
    """Pick a backend from whatever credentials are configured.

    Returns (backend, message). A None backend means nothing usable is set up,
    and the message explains what to do about it.
    """
    from src import config

    preferred = config.provider()

    gemini_key = config.gemini_api_key()
    anthropic_status, anthropic_message = config.api_key_status()

    def make_gemini():
        backend = GeminiBackend(gemini_key, config.GEMINI_MODEL, tool_schemas)
        model = backend.resolve_model()
        return backend, f"Using Google Gemini ({model}) on the free tier."

    def make_anthropic():
        return (
            AnthropicBackend(config.anthropic_api_key(), config.MODEL, tool_schemas),
            f"Using Anthropic ({config.MODEL}).",
        )

    if preferred == "gemini" and gemini_key:
        return make_gemini()
    if preferred == "anthropic" and anthropic_status == "present":
        return make_anthropic()

    # Auto: prefer whichever is actually usable, Gemini first since it is the
    # configuration that needs no billing.
    if gemini_key:
        return make_gemini()
    if anthropic_status == "present":
        return make_anthropic()

    if anthropic_status == "malformed":
        return None, f"No usable API key. {anthropic_message}"
    return None, (
        "No API key configured. Set GEMINI_API_KEY (free, from "
        "aistudio.google.com/apikey) or ANTHROPIC_API_KEY in Streamlit secrets."
    )
