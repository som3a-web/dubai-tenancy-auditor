"""The processing display.

Shows the six stages in plain language. It never shows internal tool names,
model reasoning, prompts or raw payloads — a tenant has no use for them, and
they undermine the impression of a finished service.
"""

from __future__ import annotations

import streamlit as st

from src.audit import STAGE_LABELS
from src.ui.components import esc, write


class ProgressPanel:
    """Drives a stage list and a skeleton placeholder during analysis."""

    def __init__(self) -> None:
        self._container = st.empty()
        self._skeleton = st.empty()
        self._current = 0
        self.render(0, STAGE_LABELS[0])

    def render(self, completed: int, current_label: str) -> None:
        rows = []
        for index, label in enumerate(STAGE_LABELS):
            if index < completed:
                mark, colour, weight = "&#10003;", "var(--emerald)", "500"
            elif index == completed:
                mark, colour, weight = "&#9679;", "var(--teal)", "650"
            else:
                mark, colour, weight = "&#9675;", "var(--border)", "400"
            rows.append(
                f'<li style="display:flex;gap:12px;align-items:center;padding:7px 0;'
                f'font-size:15px;font-weight:{weight};color:'
                f'{"var(--text)" if index <= completed else "var(--muted)"}">'
                f'<span style="color:{colour};width:16px">{mark}</span>{esc(label)}</li>'
            )
        percent = int(completed / len(STAGE_LABELS) * 100)
        self._container.markdown(
            '<div class="dta-card">'
            '<div style="font-weight:650;color:var(--navy);margin-bottom:6px">'
            "Analysing your contract</div>"
            '<div style="height:6px;background:#EDF1F4;border-radius:999px;'
            'margin:10px 0 14px;overflow:hidden">'
            f'<div style="height:100%;width:{percent}%;background:var(--teal);'
            'border-radius:999px"></div></div>'
            f'<ul style="list-style:none;margin:0;padding:0">{"".join(rows)}</ul>'
            "</div>",
            unsafe_allow_html=True,
        )
        self._skeleton.markdown(
            '<div class="dta-card" style="margin-top:16px">'
            + "".join(
                f'<div style="height:12px;border-radius:6px;background:#EDF1F4;'
                f'margin-bottom:10px;width:{width}%"></div>'
                for width in (100, 88, 70)
            )
            + "</div>",
            unsafe_allow_html=True,
        )

    def clear(self) -> None:
        self._container.empty()
        self._skeleton.empty()


def failure(title: str, detail: str, has_partial: bool) -> None:
    """Render a failed run without exposing internals."""
    write(
        '<div class="dta-note dta-note--risk">'
        f"<strong>{esc(_friendly_title(title))}</strong><br>{esc(_friendly_detail(detail))}"
        "</div>"
    )
    if has_partial:
        st.caption(
            "Some details were established before the analysis stopped. They are "
            "shown below, marked as incomplete."
        )


def _friendly_title(title: str) -> str:
    lowered = (title or "").lower()
    if "rate" in lowered or "429" in lowered or "resource" in lowered:
        return "The analysis service is busy"
    if "key" in lowered or "401" in lowered or "auth" in lowered:
        return "The analysis service is not configured"
    if "declin" in lowered or "refus" in lowered:
        return "This document could not be processed"
    if "ceiling" in lowered or "iteration" in lowered:
        return "The analysis stopped early"
    return "The analysis could not be completed"


def _friendly_detail(detail: str) -> str:
    """Strip anything that reads like an internal error to a non-technical user."""
    text = (detail or "").strip()
    if not text:
        return "Please try again in a moment."
    lowered = text.lower()
    if "rate limit" in lowered or "429" in lowered:
        return (
            "The service is handling a high volume of requests. Wait a moment and "
            "try again, or replay a recorded analysis from the advanced options."
        )
    if "api key" in lowered or "401" in lowered:
        return (
            "The analysis service is not available at the moment. Please try again "
            "later."
        )
    # Anything with a stack-trace or JSON smell gets replaced rather than shown.
    if any(marker in text for marker in ("{", "Traceback", "Error code", "models/")):
        return "Please try again in a moment. If this persists, try a different document."
    return text[:300]
