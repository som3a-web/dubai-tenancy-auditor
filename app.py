"""Dubai Tenancy Contract Auditor — Streamlit entry point.

The UI's job is to make the agent's work visible. Every tool call, its input, and
its result are rendered as they happen, so a judge can watch the reasoning rather
than trust a final number.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from src import __version__, agent, config, legal, llm, replay, tools
from src.agent import StepKind

SAMPLES_DIR = Path(__file__).parent / "samples"

TOOL_LABELS = {
    "parse_contract": "Reading the contract",
    "lookup_benchmark": "Finding the market benchmark",
    "calculate_legal_max": "Applying Decree 43/2013",
    "check_clauses": "Checking clauses against Dubai law",
    "generate_talking_points": "Drafting your negotiating points",
}

st.set_page_config(
    page_title="Dubai Tenancy Contract Auditor",
    page_icon="🏠",
    layout="centered",
)


# --------------------------------------------------------------------------
# Static chrome
# --------------------------------------------------------------------------


def render_header() -> None:
    st.title("Dubai Tenancy Contract Auditor")
    st.markdown(
        "**Your landlord wants to raise your rent. Is that legal?** "
        "Upload your tenancy contract and this agent works out the legal maximum "
        "increase under Dubai law, flags clauses that conflict with it, and gives "
        "you the words to push back."
    )


def render_legal_basis() -> None:
    with st.expander("The legal basis — Decree No. (43) of 2013"):
        st.markdown(
            "**Article 1** caps the annual increase by how far your rent sits below "
            "the average rental value of comparable units:"
        )
        st.table(
            {
                "Your rent vs. the index average": [
                    "Up to 10% below", "11–20% below", "21–30% below",
                    "31–40% below", "More than 40% below",
                ],
                "Maximum increase": ["0%", "5%", "10%", "15%", "20%"],
            }
        )
        st.markdown(
            "**Article 2** applies this to every landlord in Dubai, including special "
            "development zones and free zones. **Article 3** defers the benchmark to "
            "the Rent Index approved by RERA.\n\n"
            "Two further rules do a lot of work in practice: **Article 9 of Law "
            "26/2007** bars any increase before two years from the start of the "
            "original tenancy, and **Article 14** (as replaced by Law 33/2008) "
            "requires 90 days' notice to change any term.\n\n"
            f"[Read the decree]({config.DECREE_43_URL}) — Dubai Legislation portal."
        )


def render_footer(active_model: str | None = None) -> None:
    st.divider()
    prov = legal.load_benchmarks()["provenance"]
    st.caption(
        "**Guidance, not legal advice.** This tool does not replace a lawyer or the "
        "Rental Disputes Centre. The tier calculation follows Decree 43/2013; the "
        "market benchmark is an estimate and cannot reproduce RERA's building-level "
        "Smart Rental Index. Verify against the official index before acting."
    )
    st.caption(
        f"Benchmark data: {prov['label']} · confidence **{prov['confidence']}** — "
        f"v{__version__} · model `{active_model or 'none configured'}` · "
        f"{config.active_provider_summary()}"
    )


# --------------------------------------------------------------------------
# Verdict card
# --------------------------------------------------------------------------


def render_verdict(slot, payload: dict) -> None:
    """The five-second answer: their number, the legal maximum, the gap."""
    with slot.container():
        st.subheader("Verdict")

        if not payload.get("determinable"):
            st.warning(
                f"**Cannot determine the legal maximum.** {payload.get('reason', '')}"
            )
            return

        blocked = payload.get("article_9_blocks_increase")
        low, high = payload.get("max_increase_pct", [None, None])
        single = payload.get("max_increase_is_single_figure")

        if blocked:
            headline = "No increase is permitted"
            detail = (
                "Article 9 of Law 26/2007 bars any increase until "
                f"{payload.get('two_year_freeze_until')}."
            )
        elif single:
            headline = f"Legal maximum increase: {low}%"
            detail = "Under the Decree 43/2013 tier table."
        else:
            headline = f"Legal maximum increase: {low}%–{high}%"
            detail = (
                "A range, because the benchmark is an indicative estimate rather "
                "than registered-contract data."
            )

        asked = payload.get("proposed_increase_pct")
        if asked is not None and (blocked or (single and asked > (low or 0))):
            st.error(f"### {headline}\nYour landlord is asking for **{asked}%**. {detail}")
        else:
            st.info(f"### {headline}\n{detail}")

        columns = st.columns(3)
        columns[0].metric("Your rent now", f"AED {payload['current_annual_rent']:,.0f}")
        if payload.get("proposed_annual_rent"):
            columns[1].metric(
                "Landlord asking",
                f"AED {payload['proposed_annual_rent']:,.0f}",
                delta=f"{asked}%",
                delta_color="inverse",
            )
        ceiling = payload.get("max_lawful_annual_rent")
        if ceiling:
            label = f"AED {ceiling[0]:,.0f}"
            if ceiling[0] != ceiling[1]:
                label = f"AED {ceiling[0]:,.0f}–{ceiling[1]:,.0f}"
            columns[2].metric("Lawful ceiling", label)

        notice = payload.get("notice_check") or {}
        if notice.get("determinable") and notice.get("compliant") is False:
            st.warning(f"**Notice problem.** {notice.get('reason')}")

        for note in payload.get("notes", []):
            st.caption(f"· {note}")


# --------------------------------------------------------------------------
# Step rendering
# --------------------------------------------------------------------------


def render_run(steps, replay_meta: dict | None = None) -> None:
    """Render a run's steps. Identical for a live audit and a replay.

    `replay_meta` is set only when replaying, and is displayed prominently — a
    recording must never be mistaken for a live run.
    """
    st.divider()

    if replay_meta:
        recorded = str(replay_meta.get("recorded_at", ""))[:16].replace("T", " ")
        st.info(
            f"**Replay — no API call was made.** These are the exact steps a real "
            f"audit produced on {recorded or 'an earlier run'}, using "
            f"`{replay_meta.get('model', 'the configured model')}`. Nothing here "
            "is simulated; the run is replayed from a recording so the demo works "
            "without spending API quota."
        )

    verdict_slot = st.empty()
    st.subheader("What the agent did")

    open_status = None
    verdict_payload: dict | None = None
    final_text: list[str] = []

    for step in steps:
        if step.kind is StepKind.PLAN:
            st.caption(f"**Plan** — {step.body}")

        elif step.kind is StepKind.THINKING:
            with st.expander(f"Reasoning (step {step.iteration})", expanded=False):
                st.markdown(step.body)

        elif step.kind is StepKind.TOOL_CALL:
            label = TOOL_LABELS.get(step.tool_name, step.tool_name)
            open_status = st.status(f"**{label}** — `{step.tool_name}`", state="running")
            with open_status:
                st.caption("Sent to the tool:")
                st.json(step.payload, expanded=False)

        elif step.kind is StepKind.TOOL_RESULT:
            target = open_status if open_status is not None else st.status(step.title)
            with target:
                st.caption("Tool returned:")
                for key, value in step.display.items():
                    st.markdown(f"- **{key}:** {value}")
                with st.expander("Raw result", expanded=False):
                    st.json(step.payload, expanded=False)
            target.update(
                label=f"**{TOOL_LABELS.get(step.tool_name, step.tool_name)}** — "
                f"`{step.tool_name}`",
                state="error" if step.is_error else "complete",
            )
            open_status = None

            if step.tool_name == "calculate_legal_max":
                verdict_payload = step.payload
                render_verdict(verdict_slot, verdict_payload)

        elif step.kind is StepKind.TEXT:
            final_text.append(step.body)

        elif step.kind is StepKind.DONE:
            usage = step.payload
            st.caption(
                f"Finished in {usage['iterations']} steps · "
                f"{usage['total_tokens']:,} tokens · "
                f"≈ ${usage['estimated_cost_usd']:.3f}"
            )

        elif step.kind in (StepKind.ERROR, StepKind.ABORTED, StepKind.REFUSED):
            st.error(f"**{step.title}** — {step.body}")

    if final_text:
        st.divider()
        st.subheader("What this means for you")
        st.markdown("\n\n".join(final_text))


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


def sample_options() -> dict[str, Path]:
    if not SAMPLES_DIR.exists():
        return {}
    labels = {
        "sample_1_marina_1br.pdf": "Dubai Marina 1 B/R — landlord wants +15%",
        "sample_2_jvc_studio.pdf": "JVC studio — tenancy under two years old",
        "sample_3_deira_2br_scanned.pdf": "Deira 2 B/R — scanned PDF, late notice",
    }
    return {
        labels.get(p.name, p.name): p
        for p in sorted(SAMPLES_DIR.glob("*.pdf"))
    }


def main() -> None:
    render_header()
    st.divider()

    backend, provider_message = llm.build_backend(tools.TOOL_SCHEMAS)
    if backend is None:
        st.error(
            f"**No usable API key.** {provider_message}\n\n"
            "Set it in Streamlit secrets (Manage app → Settings → Secrets), then "
            "wait about a minute for it to propagate."
        )
    else:
        st.caption(f"⚙️ {provider_message}")

    samples = sample_options()
    tab_upload, tab_sample = st.tabs(["Upload your contract", "Try a sample"])

    # One place holds the chosen contract across reruns. Streamlit reruns the
    # whole script on every interaction, so local variables cannot survive the
    # gap between choosing a file and pressing the button.
    with tab_upload:
        uploaded = st.file_uploader(
            "Your tenancy contract (PDF)",
            type=["pdf"],
            help="Scanned contracts work too. The file is held in memory for this "
            "request only and is not stored.",
        )
        if uploaded is not None:
            st.session_state["contract"] = (uploaded.getvalue(), uploaded.name)

    with tab_sample:
        if samples:
            choice = st.selectbox("Pick a sample contract", list(samples))
            st.caption(
                "Synthetic contracts with no real personal data, each exercising a "
                "different part of the law."
            )
            if st.button("Use this sample"):
                path = samples[choice]
                st.session_state["contract"] = (path.read_bytes(), path.name)
        else:
            st.caption("No samples found in this deployment.")

    contract = st.session_state.get("contract")
    filename = None
    if contract is not None:
        pdf_bytes, filename = contract
        st.success(
            f"Ready to audit **{filename}** ({len(pdf_bytes) / 1024:.0f} KB) — "
            "press the button below."
        )

    recordings = replay.available()
    recording_path = recordings.get(filename) if filename else None

    live_column, replay_column = st.columns([2, 3])

    with live_column:
        live_clicked = st.button(
            "Audit my contract",
            type="primary",
            disabled=contract is None or backend is None,
        )

    with replay_column:
        replay_clicked = st.button(
            "Replay a recorded audit",
            disabled=recording_path is None,
            help=(
                "Replays a previously recorded real run with no API call. Useful "
                "when the free-tier rate limit is hit."
                if recording_path
                else "No recording exists for this contract yet."
            ),
        )

    if backend is None and recording_path is not None:
        st.info(
            "No API key is configured, but a recorded audit exists for this "
            "contract — you can still replay it."
        )

    if live_clicked and contract is not None:
        render_run(agent.run(*contract, today=date.today()))
    elif replay_clicked and recording_path is not None:
        render_run(replay.replay(recording_path), replay_meta=replay.metadata(recording_path))

    render_legal_basis()
    render_footer(active_model=backend.model if backend else None)


if __name__ == "__main__":
    main()
