"""Reusable presentation primitives.

Every function that renders contract-derived text passes it through `esc()`
first. Extracted contract content is untrusted input — a tenancy PDF could
contain markup, and it must never reach the DOM unescaped.

These render markup only. They contain no business logic and make no decisions
about what a result means; that lives in src.verdict.
"""

from __future__ import annotations

import html
from typing import Iterable, Literal

import streamlit as st

Tone = Literal["success", "warning", "risk", "neutral", "muted"]

# Inline SVG so there are no external asset requests and no emoji.
ICONS = {
    "shield": '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#102A43" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>',
    "lock": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#087F8C" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    "doc": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#087F8C" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 15h6"/></svg>',
    "check": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#18864B" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
    "alert": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#B7791F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
    "info": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#087F8C" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
}

STATUS_ICON: dict[Tone, str] = {
    "success": ICONS["check"],
    "warning": ICONS["alert"],
    "risk": ICONS["alert"],
    "neutral": ICONS["info"],
    "muted": ICONS["info"],
}


def esc(value: object, fallback: str = "—") -> str:
    """HTML-escape a value for safe rendering. Never returns None."""
    if value is None or value == "":
        return fallback
    return html.escape(str(value), quote=True)


def write(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------


def aed(value: object, fallback: str = "Not found") -> str:
    """Format an amount consistently as `AED 117,000`."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return f"AED {number:,.0f}"


def percent(value: object, fallback: str = "—", signed: bool = False) -> str:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    text = f"{number:.0f}%" if number == int(number) else f"{number:.1f}%"
    return f"+{text}" if signed and number > 0 else text


def date_label(value: object, fallback: str = "Not found") -> str:
    """Render an ISO date as `01 Sep 2025`, leaving anything else alone."""
    from datetime import date, datetime

    if value in (None, ""):
        return fallback
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date().strftime("%d %b %Y")
    except ValueError:
        return esc(value, fallback)


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------


def badge(label: str, tone: Tone = "neutral") -> str:
    return f'<span class="dta-badge dta-badge--{tone}">{esc(label)}</span>'


def note(body: str, tone: Literal["info", "warning", "risk"] = "info") -> None:
    write(f'<div class="dta-note dta-note--{tone}">{body}</div>')


def section_heading(title: str, description: str | None = None) -> None:
    st.markdown(f"### {title}")
    if description:
        write(f'<p style="color:var(--muted);margin-top:-6px">{esc(description)}</p>')


def metric_card(
    label: str,
    value: str,
    note_text: str | None = None,
    tone: Tone = "neutral",
    emphasis: bool = False,
) -> None:
    value_class = "dta-metric-value"
    if tone == "risk" and emphasis:
        value_class += " dta-metric-value--risk"
    if value in ("Not found", "—", "Unavailable"):
        value_class += " dta-metric-value--muted"
    write(
        f'<div class="dta-metric{" dta-metric--emphasis" if emphasis else ""}">'
        f'<div class="dta-metric-label">{esc(label)}</div>'
        f'<div class="{value_class}">{esc(value)}</div>'
        f'<div class="dta-metric-note">{esc(note_text, "")}</div>'
        f"</div>"
    )


def key_values(pairs: Iterable[tuple[str, object]]) -> None:
    """Render a responsive definition grid. Missing values read 'Not found'."""
    cells = []
    for label, value in pairs:
        missing = value in (None, "", "Not found")
        text = "Not found" if missing else esc(value)
        cells.append(
            f"<div><dt>{esc(label)}</dt>"
            f'<dd class="{"is-missing" if missing else ""}">{text}</dd></div>'
        )
    write(f'<dl class="dta-kv">{"".join(cells)}</dl>')


def verdict_card(
    status_label: str,
    headline: str,
    body: str,
    tone: Tone,
    meta: Iterable[tuple[str, str]] = (),
) -> None:
    meta_html = "".join(
        f"<span>{esc(label)}: <strong>{esc(value)}</strong></span>" for label, value in meta
    )
    # Built outside the f-string: an expression part cannot contain a backslash
    # before Python 3.12, and this needs escaped quotes.
    meta_block = f'<div class="dta-verdict-meta">{meta_html}</div>' if meta_html else ""
    write(
        f'<div class="dta-verdict dta-verdict--{tone}">'
        f'<div class="dta-verdict-status">{STATUS_ICON[tone]}{esc(status_label)}</div>'
        f'<h2 class="dta-verdict-title">{esc(headline)}</h2>'
        f'<p class="dta-verdict-body">{esc(body)}</p>'
        f"{meta_block}"
        f"</div>"
    )


def date_comparison(
    left_label: str, left_value: str, span_text: str, right_label: str, right_value: str
) -> None:
    write(
        '<div class="dta-timeline">'
        f'<div class="dta-timeline-node"><div class="label">{esc(left_label)}</div>'
        f'<div class="date">{esc(left_value)}</div></div>'
        f'<div class="dta-timeline-span"><div class="bar"></div>'
        f'<div style="font-size:13px;color:var(--muted)">{esc(span_text)}</div></div>'
        f'<div class="dta-timeline-node"><div class="label">{esc(right_label)}</div>'
        f'<div class="date">{esc(right_value)}</div></div>'
        "</div>"
    )


def benchmark_scale(
    low: float, high: float, markers: Iterable[tuple[str, float, str]]
) -> None:
    """Plot markers against a benchmark band.

    `markers` is (label, value, tone-colour). The axis is padded 15% either side
    of the band so a marker outside the range is still visible rather than
    clamped to the edge, which would misrepresent where it sits.
    """
    values = [value for _, value, _ in markers] + [low, high]
    axis_min, axis_max = min(values), max(values)
    padding = max((axis_max - axis_min) * 0.15, 1)
    axis_min -= padding
    axis_max += padding
    span = axis_max - axis_min or 1

    def position(value: float) -> float:
        return max(0.0, min(100.0, (value - axis_min) / span * 100))

    band = (
        f'<div class="dta-scale-band" style="left:{position(low):.1f}%;'
        f'right:{100 - position(high):.1f}%"></div>'
    )
    pins = []
    for index, (label, value, colour) in enumerate(markers):
        side = "above" if index % 2 == 0 else "below"
        pins.append(
            f'<div class="dta-scale-marker" style="left:{position(value):.1f}%;'
            f'background:{colour}">'
            f'<span class="{side}" style="color:{colour}">{esc(label)}</span></div>'
        )
    write(
        f'<div class="dta-scale"><div class="dta-scale-track">{band}{"".join(pins)}</div>'
        f'<div style="display:flex;justify-content:space-between;font-size:12px;'
        f'color:var(--muted)"><span>{aed(axis_min)}</span><span>{aed(axis_max)}</span></div>'
        f"</div>"
    )


def clause_card(
    title: str,
    risk_label: str,
    tone: Tone,
    quoted_text: str | None,
    explanation: str,
    reference: str | None,
    action: str | None,
    is_verbatim: bool = True,
) -> None:
    parts = [
        f'<div class="dta-clause dta-clause--{tone}">',
        '<div class="dta-clause-head">',
        f'<span class="dta-clause-title">{esc(title)}</span>',
        badge(risk_label, tone),
        "</div>",
    ]
    if quoted_text:
        label = "From your contract" if is_verbatim else "Summarised from your contract"
        parts.append(f'<div class="dta-clause-label">{label}</div>')
        parts.append(f'<div class="dta-quote">{esc(quoted_text)}</div>')
    parts.append(f'<div class="dta-clause-label">What this means</div>')
    parts.append(f"<p style='margin:4px 0 0'>{esc(explanation)}</p>")
    if reference:
        parts.append(f'<div class="dta-clause-label">Legal reference</div>')
        parts.append(f"<p style='margin:4px 0 0'>{esc(reference)}</p>")
    if action:
        parts.append(f'<div class="dta-clause-label">Suggested action</div>')
        parts.append(f"<p style='margin:4px 0 0'>{esc(action)}</p>")
    parts.append("</div>")
    write("".join(parts))


def source_card(
    title: str,
    source_type: Literal["official", "secondary", "internal"],
    explanation: str,
    meta: str,
    url: str | None = None,
) -> None:
    labels = {
        "official": ("Official source", "success"),
        "secondary": ("Secondary source", "neutral"),
        "internal": ("Internal estimate", "warning"),
    }
    label, tone = labels[source_type]
    css_class = "dta-source--official" if source_type == "official" else (
        "dta-source--internal" if source_type == "internal" else ""
    )
    link = (
        f'<div style="margin-top:8px"><a href="{esc(url)}" target="_blank" '
        f'rel="noopener noreferrer">View source</a></div>'
        if url
        else ""
    )
    write(
        f'<div class="dta-source {css_class}">'
        f'<div style="display:flex;justify-content:space-between;gap:12px;'
        f'align-items:center;flex-wrap:wrap">'
        f'<span class="dta-source-title">{esc(title)}</span>{badge(label, tone)}</div>'
        f'<p style="margin:6px 0 0;font-size:14px">{esc(explanation)}</p>'
        f'<div class="dta-source-meta">{esc(meta)}</div>{link}</div>'
    )


def skeleton(lines: int = 3) -> str:
    """Placeholder blocks so a pending panel does not look frozen."""
    bars = "".join(
        f'<div style="height:12px;border-radius:6px;background:#E9EEF2;'
        f'margin-bottom:10px;width:{width}%"></div>'
        for width in (100, 82, 64)[:lines]
    )
    return f'<div class="dta-card">{bars}</div>'
