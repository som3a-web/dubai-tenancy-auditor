"""Collects the agent's step stream into a structured result.

This is the seam between the agent and the interface. The agent emits a stream
of Steps; the UI needs a finished object it can lay out. Putting that
translation here means the interface never touches raw tool payloads or model
reasoning, and the agent never knows anything about presentation.

Reasoning steps are deliberately dropped. They are internal working, not
findings, and showing them to a tenant would be noise at best.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from src.agent import Step, StepKind

# The six stages shown to the user, in order. The keys are the internal tool
# names; the labels are what a tenant actually reads.
STAGES: list[tuple[str, str]] = [
    ("parse_contract", "Reading contract"),
    ("parse_contract", "Extracting tenancy details"),
    ("calculate_legal_max", "Checking notice requirements"),
    ("lookup_benchmark", "Comparing rental benchmark"),
    ("check_clauses", "Reviewing clauses"),
    ("generate_talking_points", "Preparing findings"),
]

STAGE_LABELS = [label for _, label in STAGES]

# Which stage index each tool completion should advance us to.
_TOOL_PROGRESS = {
    "parse_contract": 2,
    "lookup_benchmark": 4,
    "calculate_legal_max": 3,
    "check_clauses": 5,
    "generate_talking_points": 6,
}


@dataclass
class AuditResult:
    """Everything the interface needs, and nothing it does not."""

    contract: dict = field(default_factory=dict)
    benchmark: dict = field(default_factory=dict)
    calculation: dict = field(default_factory=dict)
    clauses: dict = field(default_factory=dict)
    response: dict = field(default_factory=dict)

    narrative: str = ""
    usage: dict = field(default_factory=dict)

    failed: bool = False
    failure_title: str = ""
    failure_detail: str = ""

    is_replay: bool = False
    replay_meta: dict = field(default_factory=dict)

    @property
    def completed(self) -> bool:
        return bool(self.calculation) and not self.failed

    @property
    def has_partial_findings(self) -> bool:
        """True when something useful survived even though the run did not finish."""
        return self.failed and bool(self.contract or self.calculation)

    def field_value(self, *path: str, default: Any = None) -> Any:
        node: Any = self.contract
        for key in path:
            if not isinstance(node, dict):
                return default
            node = node.get(key)
        return node if node not in (None, "") else default


def collect(
    steps: Iterator[Step],
    on_progress: Callable[[int, str], None] | None = None,
    replay_meta: dict | None = None,
) -> AuditResult:
    """Drain the agent's steps into an AuditResult.

    `on_progress(stage_index, label)` is called as stages complete so the caller
    can drive a progress display without knowing anything about tools.
    """
    result = AuditResult(is_replay=bool(replay_meta), replay_meta=replay_meta or {})
    narrative_parts: list[str] = []

    if on_progress:
        on_progress(0, STAGE_LABELS[0])

    for step in steps:
        if step.kind is StepKind.THINKING:
            # Internal working. Never surfaced.
            continue

        if step.kind is StepKind.TOOL_RESULT:
            payload = step.payload or {}
            if step.tool_name == "parse_contract":
                result.contract = payload
            elif step.tool_name == "lookup_benchmark":
                result.benchmark = payload
            elif step.tool_name == "calculate_legal_max":
                result.calculation = payload
            elif step.tool_name == "check_clauses":
                result.clauses = payload
            elif step.tool_name == "generate_talking_points":
                result.response = payload

            if on_progress:
                reached = _TOOL_PROGRESS.get(step.tool_name)
                if reached is not None:
                    label = STAGE_LABELS[min(reached, len(STAGE_LABELS) - 1)]
                    on_progress(reached, label)

        elif step.kind is StepKind.TEXT:
            narrative_parts.append(step.body)

        elif step.kind is StepKind.DONE:
            result.usage = step.payload or {}
            if on_progress:
                on_progress(len(STAGE_LABELS), "Complete")

        elif step.kind in (StepKind.ERROR, StepKind.ABORTED, StepKind.REFUSED):
            result.failed = True
            result.failure_title = step.title
            result.failure_detail = step.body

    result.narrative = "\n\n".join(part.strip() for part in narrative_parts if part.strip())
    return result


# --------------------------------------------------------------------------
# Views onto the result
# --------------------------------------------------------------------------


def extracted_fields(result: AuditResult) -> list[tuple[str, str, Any]]:
    """(key, label, value) for the contract details grid.

    Values are returned raw; the UI decides how to format and escape them.
    """
    dates = result.contract.get("dates") or {}
    return [
        ("area", "Property area", result.contract.get("area_canonical")
         or result.contract.get("area_as_written")),
        ("size", "Unit type", _size_label(result.contract.get("size_normalised"))),
        ("annual_rent", "Current annual rent", result.contract.get("annual_rent")),
        ("proposed_rent", "Proposed annual rent", result.contract.get("proposed_rent")),
        ("contract_start", "Contract start", dates.get("contract_start")),
        ("contract_expiry", "Contract expiry", dates.get("contract_expiry")),
        ("original_occupancy_start", "First occupied", dates.get("original_occupancy_start")),
        ("notice_served", "Notice served", dates.get("notice_served")),
    ]


def _size_label(size: str | None) -> str | None:
    return {
        "studio": "Studio",
        "1br": "1 bedroom",
        "2br": "2 bedrooms",
        "3br": "3 bedrooms",
    }.get(size or "", size)


def unresolved_fields(result: AuditResult) -> list[str]:
    return list(result.contract.get("unresolved") or [])


def open_questions(result: AuditResult) -> list[str]:
    return list(result.response.get("cannot_determine") or [])
