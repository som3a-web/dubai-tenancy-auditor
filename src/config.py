"""Runtime configuration and cost ceilings.

Secrets resolve from Streamlit secrets first, then the environment, so the app
runs identically on Streamlit Community Cloud and on a laptop.
"""

from __future__ import annotations

import os

MODEL = "claude-opus-5"

# Hard ceilings. The agent loop aborts loudly when either is exceeded rather
# than retrying — a runaway loop at 3am is how you lose the API budget.
DEFAULT_MAX_TOKENS_PER_RUN = 250_000
DEFAULT_MAX_AGENT_ITERATIONS = 8

# Displayed in the UI next to every benchmark figure. See README limitations.
BENCHMARK_SNAPSHOT_DATE = "pending"
BENCHMARK_SOURCE = "pending"

DECREE_43_URL = (
    "https://dlp.dubai.gov.ae/Legislation%20Reference/2013/"
    "Decree%20No.%20(43)%20of%202013%20Determining%20Rent%20Increase%20for%20Real%20Property.html"
)

TOOL_SEQUENCE = [
    ("parse_contract", "Read the contract"),
    ("lookup_benchmark", "Find the market benchmark"),
    ("calculate_legal_max", "Apply Decree 43/2013"),
    ("check_clauses", "Check clauses against Dubai tenancy law"),
    ("generate_talking_points", "Draft your negotiating points"),
]


def _secret(name: str) -> str | None:
    """Read a secret from Streamlit secrets, falling back to the environment."""
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        # No Streamlit context, or no secrets.toml present locally. Fall through.
        pass
    return os.environ.get(name)


def anthropic_api_key() -> str | None:
    return _secret("ANTHROPIC_API_KEY")


def _int_secret(name: str, default: int) -> int:
    raw = _secret(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def max_tokens_per_run() -> int:
    return _int_secret("MAX_TOKENS_PER_RUN", DEFAULT_MAX_TOKENS_PER_RUN)


def max_agent_iterations() -> int:
    return _int_secret("MAX_AGENT_ITERATIONS", DEFAULT_MAX_AGENT_ITERATIONS)
