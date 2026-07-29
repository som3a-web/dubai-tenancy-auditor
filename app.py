"""Dubai Tenancy Contract Auditor — Streamlit entry point.

Phase 1 skeleton: the real UI shell, wired to nothing. Deployed early and
deliberately, so the deployment pipeline is proven while it is still trivial.
"""

from __future__ import annotations

import streamlit as st

from src import __version__, config

st.set_page_config(
    page_title="Dubai Tenancy Contract Auditor",
    page_icon="🏠",
    layout="centered",
)


def render_header() -> None:
    st.title("Dubai Tenancy Contract Auditor")
    st.markdown(
        "**Your landlord wants to raise your rent. Is that legal?** "
        "Upload your tenancy contract and this agent works out the legal maximum "
        "increase under Dubai law, flags clauses that conflict with it, and gives "
        "you the words to push back."
    )


def render_upload() -> None:
    st.file_uploader(
        "Your tenancy contract (PDF)",
        type=["pdf"],
        help="Scanned contracts work too. The file is held in memory for this "
        "request only and is not stored.",
        disabled=True,
    )
    st.button("Audit my contract", type="primary", disabled=True)
    st.caption("⚙️ Skeleton deployment — the agent is wired up in the next build phase.")


def render_planned_steps() -> None:
    """The agentic loop, shown up front so the shape of the work is visible."""
    st.subheader("How the agent works")
    for index, (tool_name, plain_english) in enumerate(config.TOOL_SEQUENCE, start=1):
        st.markdown(f"**{index}. {plain_english}** — `{tool_name}`")


def render_legal_basis() -> None:
    with st.expander("The legal basis — Decree No. (43) of 2013"):
        st.markdown(
            "**Article 1** caps the annual increase by how far your rent sits below "
            "the average rental value of comparable units:"
        )
        st.table(
            {
                "Your rent vs. the index average": [
                    "Up to 10% below",
                    "11–20% below",
                    "21–30% below",
                    "31–40% below",
                    "More than 40% below",
                ],
                "Maximum increase": ["0%", "5%", "10%", "15%", "20%"],
            }
        )
        st.markdown(
            "**Article 2** applies this to every landlord in Dubai, including "
            "special development zones and free zones. **Article 3** defers the "
            "benchmark to the Rent Index approved by RERA.\n\n"
            f"[Read the decree]({config.DECREE_43_URL}) — Dubai Legislation portal."
        )


def render_footer() -> None:
    st.divider()
    st.caption(
        "**Guidance, not legal advice.** This tool does not replace a lawyer or the "
        "Rental Disputes Centre. The tier calculation follows Decree 43/2013 exactly; "
        "the market benchmark is an estimate from a dated snapshot of DLD registered "
        "contracts and cannot reproduce RERA's building-level Smart Rental Index. "
        "Verify against the official index before acting."
    )
    key_state = "configured" if config.anthropic_api_key() else "not configured"
    st.caption(f"v{__version__} · model `{config.MODEL}` · API key {key_state}")


def main() -> None:
    render_header()
    st.divider()
    render_upload()
    st.divider()
    render_planned_steps()
    render_legal_basis()
    render_footer()


if __name__ == "__main__":
    main()
