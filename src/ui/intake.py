"""Document intake: upload, sample selection, and the demo replay option."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src import replay
from src.ui.components import ICONS, esc, write

MAX_UPLOAD_MB = 15
SAMPLE_LABELS = {
    "sample_1_marina_1br.pdf": "Dubai Marina · 1 bedroom · 15% increase requested",
    "sample_2_jvc_studio.pdf": "Jumeirah Village Circle · studio · tenancy under two years",
    "sample_3_deira_2br_scanned.pdf": "Deira · 2 bedrooms · scanned document, late notice",
}

PRIVACY_LINE = (
    "Your document is processed in memory for this analysis only. It is not "
    "written to disk, not retained afterwards, and its contents are not logged."
)


def _validate(uploaded) -> str | None:
    """Return an error message, or None if the file is acceptable."""
    if uploaded is None:
        return None
    size_mb = uploaded.size / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        return (
            f"This file is {size_mb:.1f} MB, above the {MAX_UPLOAD_MB} MB limit. "
            "Try exporting a smaller copy or splitting the document."
        )
    if uploaded.size == 0:
        return "This file is empty. Please check the export and try again."
    head = uploaded.getvalue()[:5]
    if not head.startswith(b"%PDF"):
        return (
            "This does not look like a valid PDF. If it was renamed from another "
            "format, export it as PDF and try again."
        )
    return None


def samples_available(samples_dir: Path) -> dict[str, Path]:
    if not samples_dir.exists():
        return {}
    return {
        SAMPLE_LABELS.get(path.name, path.name): path
        for path in sorted(samples_dir.glob("*.pdf"))
    }


def render(samples_dir: Path, analysis_enabled: bool) -> tuple[bytes, str] | None:
    """Draw the intake card. Returns (pdf bytes, filename) when analysis starts."""
    st.markdown("## Upload your tenancy contract")

    uploaded = st.file_uploader(
        "Drag and drop your contract, or browse",
        type=["pdf"],
        help=f"PDF only, up to {MAX_UPLOAD_MB} MB. Scanned documents are supported.",
        label_visibility="visible",
    )

    error = _validate(uploaded)
    if error:
        write(f'<div class="dta-note dta-note--risk">{esc(error)}</div>')
        uploaded = None
    elif uploaded is not None:
        st.session_state["contract"] = (uploaded.getvalue(), uploaded.name)

    contract = st.session_state.get("contract")

    # One selected-file row — no separate success banner repeating the name.
    if contract:
        pdf_bytes, filename = contract
        row, remove = st.columns([8, 2], vertical_alignment="center")
        with row:
            write(
                '<div style="display:flex;align-items:center;gap:10px">'
                f'{ICONS["check"]}<span style="font-weight:600">{esc(filename)}</span>'
                f'<span style="color:var(--muted);font-size:13px">'
                f"{len(pdf_bytes) / 1024:,.0f} KB</span></div>"
            )
        with remove:
            if st.button("Remove", use_container_width=True, key="remove_file"):
                st.session_state.pop("contract", None)
                st.session_state.pop("result", None)
                st.rerun()

    write(f'<p style="font-size:13px;color:var(--muted);margin-top:10px">{esc(PRIVACY_LINE)}</p>')

    start = st.button(
        "Analyse contract",
        type="primary",
        use_container_width=True,
        disabled=contract is None or not analysis_enabled,
    )

    samples = samples_available(samples_dir)
    if samples:
        with st.expander("Use a sample contract instead"):
            st.caption(
                "Synthetic contracts containing no real personal data, each "
                "illustrating a different aspect of Dubai tenancy law."
            )
            choice = st.selectbox("Sample", list(samples), label_visibility="collapsed")
            if st.button("Load this sample", use_container_width=True):
                path = samples[choice]
                st.session_state["contract"] = (path.read_bytes(), path.name)
                st.session_state.pop("result", None)
                st.rerun()

    _advanced_options(contract)

    if start and contract:
        return contract
    return None


def _advanced_options(contract) -> None:
    """Replay lives here — useful for demos, but not a primary user action."""
    recordings = replay.available()
    if not recordings:
        return

    with st.expander("Advanced demo options"):
        st.caption(
            "Replays a previously recorded analysis without contacting the "
            "analysis service. Intended for demonstrations and for when the "
            "service is rate limited."
        )
        filename = contract[1] if contract else None
        path = recordings.get(filename) if filename else None
        if st.button(
            "Replay recorded analysis",
            disabled=path is None,
            help=None if path else "No recording exists for the selected document.",
        ):
            st.session_state["replay_request"] = str(path)
            st.rerun()
