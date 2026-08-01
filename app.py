"""Dubai Tenancy Contract Auditor — application entry point.

This module orchestrates only: page setup, session state, and the sequence of
screens. Presentation lives in src/ui, the result model in src/audit, the
conclusion logic in src/verdict, and the legal rules in src/legal.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src import agent, audit, legal, llm, replay, report, theme, tools
from src.ui import intake, layout, progress, results

SAMPLES_DIR = Path(__file__).parent / "samples"

st.set_page_config(
    page_title="Dubai Tenancy Contract Auditor",
    page_icon="🛡",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _init_state() -> None:
    st.session_state.setdefault("language", "English")
    st.session_state.setdefault("corrections", {})


def _reset() -> None:
    for key in ("contract", "result", "result_filename", "corrections",
                "replay_request", "response_draft"):
        st.session_state.pop(key, None)
    # The draft widget is keyed per language and tone, so clear every variant
    # rather than one fixed name.
    for key in [k for k in st.session_state if str(k).startswith("response_draft_")]:
        st.session_state.pop(key, None)


def _run_analysis(pdf_bytes: bytes, filename: str) -> audit.AuditResult:
    panel = progress.ProgressPanel()
    try:
        result = audit.collect(
            agent.run(pdf_bytes, filename=filename),
            on_progress=panel.render,
        )
    finally:
        panel.clear()
    return result


def _run_replay(path_str: str) -> audit.AuditResult:
    path = Path(path_str)
    meta = replay.metadata(path)
    panel = progress.ProgressPanel()
    try:
        result = audit.collect(
            replay.replay(path, pace_seconds=0.25),
            on_progress=panel.render,
            replay_meta=meta,
        )
    finally:
        panel.clear()
    return result


def _render_results(result: audit.AuditResult, filename: str) -> None:
    if result.is_replay:
        recorded = str(result.replay_meta.get("recorded_at", ""))[:16].replace("T", " ")
        st.info(
            f"Replay of a previously recorded analysis from {recorded or 'an earlier run'}. "
            "No new analysis was performed.",
        )

    if result.failed:
        progress.failure(result.failure_title, result.failure_detail,
                         result.has_partial_findings)
        if not result.has_partial_findings:
            if st.button("Start a new audit", type="primary"):
                _reset()
                st.rerun()
            return

    decision = results.verdict_section(result)
    st.write("")
    results.financial_summary(result)
    st.write("")
    results.detail_tabs(result, decision)

    st.divider()
    _actions(result, filename)


def _actions(result: audit.AuditResult, filename: str) -> None:
    response_text = st.session_state.get("response_draft") or results.build_response(result)

    primary, secondary, tertiary, quaternary = st.columns(4)

    with primary:
        st.download_button(
            "Copy response to landlord",
            data=response_text,
            file_name="response-to-landlord.txt",
            mime="text/plain",
            type="primary",
            use_container_width=True,
            disabled=not response_text.strip(),
            help=None if response_text.strip() else "No response draft is available.",
        )

    with secondary:
        pdf_bytes, error = _build_report(result, filename, response_text)
        st.download_button(
            "Download PDF report",
            data=pdf_bytes or b"",
            file_name=f"tenancy-analysis-{report.audit_reference(result, filename)}.pdf",
            mime="application/pdf",
            use_container_width=True,
            disabled=pdf_bytes is None,
            help=error,
        )

    with tertiary:
        st.link_button(
            "Verify official rental index",
            "https://dubailand.gov.ae/en/eservices/rental-index/",
            use_container_width=True,
        )

    with quaternary:
        if st.button("Start new audit", use_container_width=True):
            _reset()
            st.rerun()


@st.cache_data(show_spinner=False, max_entries=4)
def _cached_report(cache_key: str, _result: audit.AuditResult, filename: str,
                   response_text: str) -> bytes:
    """Cache on an explicit key so an identical run is not re-rendered.

    The result object is excluded from hashing (leading underscore) because it
    contains contract-derived content that should not become a cache key.
    """
    return report.build(_result, filename, response_text)


def _build_report(result: audit.AuditResult, filename: str,
                  response_text: str) -> tuple[bytes | None, str | None]:
    try:
        key = f"{report.audit_reference(result, filename)}|{hash(response_text)}"
        return _cached_report(key, result, filename, response_text), None
    except Exception:
        return None, "The report could not be generated for this analysis."


def main() -> None:
    theme.inject()
    _init_state()

    has_result = "result" in st.session_state
    language, new_audit = layout.header(has_result, st.session_state["language"])
    st.session_state["language"] = language

    if new_audit:
        _reset()
        st.rerun()

    # Say plainly what the language control does. It changes the response draft,
    # not the legal analysis — without this the selector looks broken, because
    # switching it appears to change nothing until you open the draft tab.
    if language == "العربية":
        st.info(
            "الواجهة والتحليل القانوني باللغة الإنجليزية. اختيار العربية يغيّر "
            "**مسودة الرد على المالك** في تبويب «Response Draft» فقط."
        )

    backend, provider_message = llm.build_backend(tools.TOOL_SCHEMAS)
    analysis_enabled = backend is not None

    if has_result:
        result = st.session_state["result"]
        filename = st.session_state.get("result_filename", "contract.pdf")
        _render_results(result, filename)
        layout.footer(legal.load_benchmarks().get("provenance", {}))
        return

    layout.hero()
    st.write("")

    if not analysis_enabled and not replay.available():
        st.warning(
            "The analysis service is not available at the moment. Please try again "
            "later.",
        )
    elif not analysis_enabled:
        st.info(
            "Live analysis is unavailable right now, but a recorded analysis can be "
            "replayed from the advanced options below.",
        )

    requested = intake.render(SAMPLES_DIR, analysis_enabled)

    # Render results in the SAME run rather than storing and calling st.rerun().
    # An analysis takes up to a minute, and if the websocket reconnects in that
    # window Streamlit starts a fresh session — the stored result disappears and
    # the user lands back on an empty upload screen having waited for nothing.
    # Rendering inline means the result reaches the page even if the session is
    # later lost; session state is still written so reruns after this one work.
    if st.session_state.get("replay_request"):
        path_str = st.session_state.pop("replay_request")
        result = _run_replay(path_str)
        st.session_state["result"] = result
        st.session_state["result_filename"] = Path(path_str).stem + ".pdf"
        _render_results(result, st.session_state["result_filename"])
        layout.footer(legal.load_benchmarks().get("provenance", {}))
        return

    if requested:
        pdf_bytes, filename = requested
        result = _run_analysis(pdf_bytes, filename)
        st.session_state["result"] = result
        st.session_state["result_filename"] = filename
        _render_results(result, filename)
        layout.footer(legal.load_benchmarks().get("provenance", {}))
        return

    layout.footer(legal.load_benchmarks().get("provenance", {}))


if __name__ == "__main__":
    main()
