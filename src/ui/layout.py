"""Page chrome: header, hero and footer."""

from __future__ import annotations

import streamlit as st

from src import __version__, config
from src.ui.components import ICONS, esc, write

DISCLAIMER = (
    "This tool provides automated informational analysis and is not a substitute "
    "for advice from a qualified legal professional or confirmation through the "
    "relevant official authority."
)

TRUST_POINTS = [
    (ICONS["lock"], "Secure document processing"),
    (ICONS["doc"], "Evidence-based analysis"),
    (ICONS["info"], "Official verification clearly identified"),
]

HOW_IT_WORKS = [
    "Upload your tenancy contract",
    "Review the details we extracted",
    "Receive the analysis and a response draft",
]


def header(show_new_audit: bool, language: str) -> tuple[str, bool]:
    """Render the header. Returns (selected language, new-audit pressed).

    Deliberately shows no model name, provider, framework or author — that is
    implementation detail and it undermines the impression of a service.
    """
    left, middle, right = st.columns([6, 2.1, 2.4], vertical_alignment="center")

    with left:
        write(
            '<div class="dta-brand">'
            f'{ICONS["shield"]}'
            "<div><div class=\"dta-brand-name\">Dubai Tenancy Contract Auditor</div>"
            '<div class="dta-brand-sub">Rent increase and contract review</div></div>'
            "</div>"
        )

    with middle:
        # Key only, no index. Passing both makes Streamlit ignore `index` after
        # the first render and silently use whatever is stored under the key,
        # which drifts out of sync with our own state.
        st.session_state.setdefault("language_select", language)
        chosen = st.selectbox(
            "Language",
            options=["English", "العربية"],
            label_visibility="collapsed",
            key="language_select",
        )

    with right:
        pressed = False
        if show_new_audit:
            pressed = st.button("New audit", use_container_width=True, key="new_audit_top")
        else:
            write(
                '<div style="text-align:right;font-size:13px">'
                '<a href="#privacy">Privacy</a></div>'
            )

    st.divider()
    return chosen, pressed


def hero() -> None:
    left, right = st.columns([1.35, 1], gap="large")

    with left:
        write('<div class="dta-hero-eyebrow">Dubai tenancy law</div>')
        st.markdown("# Check your Dubai rent increase before you respond")
        write(
            '<p class="dta-hero-lede">We review your tenancy contract, the increase '
            "your landlord has requested, whether notice was served in time, and the "
            "clauses that affect your position — then set out what you can say in "
            "reply.</p>"
        )
        write(
            '<div class="dta-trust">'
            + "".join(
                f'<span class="dta-trust-item">{icon}{esc(label)}</span>'
                for icon, label in TRUST_POINTS
            )
            + "</div>"
        )

    with right:
        write(
            '<div class="dta-card">'
            '<div style="font-weight:650;color:var(--navy);margin-bottom:10px">'
            "How it works</div>"
            '<ol class="dta-steps">'
            + "".join(f"<li>{esc(step)}</li>" for step in HOW_IT_WORKS)
            + "</ol></div>"
        )

    st.write("")
    write(f'<div class="dta-note dta-note--info">{esc(DISCLAIMER)}</div>')


def footer(benchmark_provenance: dict) -> None:
    review_date = config.legal_review_date()
    review_line = (
        f"Last legal-content review: <strong>{esc(review_date)}</strong>. "
        if review_date
        else ""
    )
    write(
        '<div class="dta-footer" id="privacy">'
        f"<p><strong>Informational use only.</strong> {esc(DISCLAIMER)}</p>"
        "<p><strong>Privacy.</strong> Uploaded contracts are held in memory for the "
        "duration of the analysis and are not written to disk or retained afterwards. "
        "Document contents are not logged.</p>"
        "<p><strong>Data sources.</strong> Legal provisions are quoted from the Dubai "
        "Legislation Portal. The market benchmark is "
        f"<strong>{esc(benchmark_provenance.get('label', 'not available'))}</strong> "
        f"(confidence: {esc(benchmark_provenance.get('confidence', 'unknown'))}). "
        "It is not RERA's official building-level Smart Rental Index and cannot "
        "reproduce it.</p>"
        f"<p>{review_line}Version {esc(__version__)}.</p>"
        "</div>"
    )
