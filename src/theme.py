"""Design tokens and the single stylesheet injection.

All CSS lives here so there is one place to change the look. Selectors target
Streamlit's stable `data-testid` attributes and our own class names rather than
generated emotion-cache classes, which change between Streamlit releases.
"""

from __future__ import annotations

import streamlit as st

# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

NAVY = "#102A43"
TEAL = "#087F8C"
EMERALD = "#18864B"
AMBER = "#B7791F"
RED = "#C53030"

BACKGROUND = "#F5F7FA"
SURFACE = "#FFFFFF"
TEXT = "#17212B"
TEXT_MUTED = "#5F6B76"
BORDER = "#DCE3E8"

STATUS_COLOURS = {
    "success": EMERALD,
    "warning": AMBER,
    "risk": RED,
    "neutral": TEAL,
    "muted": TEXT_MUTED,
}


def _css() -> str:
    return f"""
:root {{
  --navy: {NAVY};
  --teal: {TEAL};
  --emerald: {EMERALD};
  --amber: {AMBER};
  --red: {RED};
  --bg: {BACKGROUND};
  --surface: {SURFACE};
  --text: {TEXT};
  --muted: {TEXT_MUTED};
  --border: {BORDER};
  --radius: 14px;
  --radius-sm: 10px;
  --s1: 8px;  --s2: 16px; --s3: 24px; --s4: 32px; --s5: 40px; --s6: 48px;
  --shadow: 0 1px 2px rgba(16,42,67,.04), 0 4px 12px rgba(16,42,67,.05);
}}

html, body, [data-testid="stAppViewContainer"] {{
  background: var(--bg);
  color: var(--text);
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI",
               "Helvetica Neue", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.55;
}}

/* Streamlit's default top padding wastes the first screenful. */
[data-testid="stAppViewContainer"] > .main .block-container {{
  max-width: 1220px;
  padding-top: var(--s3);
  padding-bottom: var(--s6);
}}

[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer {{ visibility: hidden; }}

h1, h2, h3, h4 {{ color: var(--navy); font-weight: 650; letter-spacing: -.011em; }}
h1 {{ font-size: 44px; line-height: 1.12; margin: 0 0 var(--s2); }}
h2 {{ font-size: 28px; line-height: 1.2; margin: var(--s4) 0 var(--s2); }}
h3 {{ font-size: 20px; margin: var(--s3) 0 var(--s1); }}
p  {{ color: var(--text); }}

a {{ color: var(--teal); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* ---------------------------------------------------------------- surfaces */

.dta-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--s3);
  box-shadow: var(--shadow);
}}
.dta-card + .dta-card {{ margin-top: var(--s2); }}
.dta-card--flush {{ padding: var(--s2) var(--s3); }}

.dta-header {{
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--s2); flex-wrap: wrap;
  padding: var(--s2) var(--s3);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: var(--s3);
}}
.dta-brand {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
.dta-brand svg {{ flex: 0 0 auto; }}
.dta-brand-name {{
  font-weight: 650; color: var(--navy); font-size: 17px; line-height: 1.25;
}}
.dta-brand-sub {{ font-size: 13px; color: var(--muted); }}
.dta-header-actions {{ display: flex; align-items: center; gap: var(--s2); }}

/* ------------------------------------------------------------------- hero */

.dta-hero-eyebrow {{
  text-transform: uppercase; letter-spacing: .09em;
  font-size: 12px; font-weight: 650; color: var(--teal);
  margin-bottom: var(--s1);
}}
.dta-hero-lede {{ font-size: 18px; color: var(--muted); max-width: 56ch; }}

.dta-trust {{ display: flex; flex-wrap: wrap; gap: var(--s2); margin-top: var(--s3); }}
.dta-trust-item {{
  display: flex; align-items: center; gap: 8px;
  font-size: 14px; color: var(--text);
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 999px; padding: 7px 14px;
}}
.dta-trust-item svg {{ flex: 0 0 auto; }}

.dta-steps {{ counter-reset: dta-step; margin: 0; padding: 0; list-style: none; }}
.dta-steps li {{
  counter-increment: dta-step;
  display: flex; gap: 12px; align-items: flex-start;
  padding: 10px 0; border-bottom: 1px solid var(--border);
  font-size: 15px;
}}
.dta-steps li:last-child {{ border-bottom: 0; padding-bottom: 0; }}
.dta-steps li::before {{
  content: counter(dta-step);
  flex: 0 0 24px; height: 24px; border-radius: 50%;
  background: var(--navy); color: #fff;
  font-size: 12px; font-weight: 650;
  display: inline-flex; align-items: center; justify-content: center;
}}

/* ---------------------------------------------------------------- verdict */

.dta-verdict {{
  border-radius: var(--radius);
  border: 1px solid var(--border);
  border-left: 5px solid var(--teal);
  background: var(--surface);
  padding: var(--s3);
  box-shadow: var(--shadow);
}}
.dta-verdict--success {{ border-left-color: var(--emerald); }}
.dta-verdict--warning {{ border-left-color: var(--amber); }}
.dta-verdict--risk    {{ border-left-color: var(--red); }}
.dta-verdict-status {{
  display: flex; align-items: center; gap: 10px;
  font-size: 13px; font-weight: 650; text-transform: uppercase;
  letter-spacing: .07em; color: var(--muted); margin-bottom: 10px;
}}
.dta-verdict-title {{
  font-size: 30px; line-height: 1.22; font-weight: 650;
  color: var(--navy); margin: 0 0 10px;
}}
.dta-verdict-body {{ font-size: 17px; color: var(--text); margin: 0; max-width: 72ch; }}
.dta-verdict-meta {{
  display: flex; flex-wrap: wrap; gap: var(--s2);
  margin-top: var(--s3); padding-top: var(--s2);
  border-top: 1px solid var(--border);
  font-size: 13px; color: var(--muted);
}}
.dta-verdict-meta span strong {{ color: var(--text); font-weight: 600; }}

/* ----------------------------------------------------------------- badges */

.dta-badge {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 650; letter-spacing: .02em;
  padding: 4px 10px; border-radius: 999px;
  border: 1px solid transparent; white-space: nowrap;
}}
.dta-badge--success {{ background:#E8F5EE; color:{EMERALD}; border-color:#BFE3CE; }}
.dta-badge--warning {{ background:#FDF5E6; color:{AMBER}; border-color:#F0DDB4; }}
.dta-badge--risk    {{ background:#FDECEC; color:{RED};   border-color:#F5C6C6; }}
.dta-badge--neutral {{ background:#E9F3F4; color:{TEAL};  border-color:#BFDDE0; }}
.dta-badge--muted   {{ background:#EEF1F4; color:{TEXT_MUTED}; border-color:var(--border); }}

/* ---------------------------------------------------------------- metrics */

.dta-metric {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: var(--s2) var(--s3);
  height: 100%; display: flex; flex-direction: column; gap: 6px;
}}
.dta-metric--emphasis {{ border-color: #F0C9C9; background: #FFFBFB; }}
.dta-metric-label {{
  font-size: 13px; font-weight: 600; color: var(--muted);
  text-transform: uppercase; letter-spacing: .05em;
}}
.dta-metric-value {{
  font-size: 30px; font-weight: 650; color: var(--navy);
  line-height: 1.15; font-variant-numeric: tabular-nums;
}}
.dta-metric-value--risk {{ color: var(--red); }}
.dta-metric-value--muted {{ color: var(--muted); font-size: 22px; }}
.dta-metric-note {{ font-size: 13px; color: var(--muted); margin-top: auto; }}

/* --------------------------------------------------------------- key/value */

.dta-kv {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1px; background: var(--border);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  overflow: hidden;
}}
.dta-kv > div {{ background: var(--surface); padding: 12px var(--s2); }}
.dta-kv dt {{
  font-size: 12px; font-weight: 600; color: var(--muted);
  text-transform: uppercase; letter-spacing: .05em; margin: 0 0 3px;
}}
.dta-kv dd {{ margin: 0; font-size: 15px; color: var(--text); word-break: break-word; }}
.dta-kv dd.is-missing {{ color: var(--muted); font-style: italic; }}

/* -------------------------------------------------------------- benchmark */

.dta-scale {{ margin: var(--s2) 0 var(--s3); }}
.dta-scale-track {{
  position: relative; height: 10px; border-radius: 999px;
  background: linear-gradient(90deg,#E6EBF0 0%, #E9F3F4 100%);
  margin: 34px 0 30px;
}}
.dta-scale-band {{
  position: absolute; top: 0; bottom: 0;
  background: #CDE7EA; border-radius: 999px;
}}
.dta-scale-marker {{ position: absolute; top: -8px; width: 2px; height: 26px; }}
.dta-scale-marker span {{
  position: absolute; left: 50%; transform: translateX(-50%);
  white-space: nowrap; font-size: 12px; font-weight: 600;
}}
.dta-scale-marker span.below {{ top: 28px; }}
.dta-scale-marker span.above {{ bottom: 28px; }}

/* --------------------------------------------------------------- timeline */

.dta-timeline {{
  display: grid; grid-template-columns: 1fr auto 1fr;
  align-items: center; gap: var(--s2); margin: var(--s2) 0;
}}
.dta-timeline-node {{ text-align: center; }}
.dta-timeline-node .date {{ font-size: 17px; font-weight: 650; color: var(--navy); }}
.dta-timeline-node .label {{
  font-size: 12px; color: var(--muted);
  text-transform: uppercase; letter-spacing: .05em;
}}
.dta-timeline-span {{ text-align: center; min-width: 150px; }}
.dta-timeline-span .bar {{
  height: 2px; background: var(--border); margin: 8px 0; position: relative;
}}
.dta-timeline-span .bar::before, .dta-timeline-span .bar::after {{
  content: ""; position: absolute; top: -3px; width: 8px; height: 8px;
  border-radius: 50%; background: var(--border);
}}
.dta-timeline-span .bar::before {{ left: 0; }}
.dta-timeline-span .bar::after {{ right: 0; }}

/* ---------------------------------------------------------------- clauses */

.dta-clause {{
  border: 1px solid var(--border); border-left: 4px solid var(--border);
  border-radius: var(--radius-sm); background: var(--surface);
  padding: var(--s2) var(--s3); margin-bottom: var(--s2);
}}
.dta-clause--risk    {{ border-left-color: var(--red); }}
.dta-clause--warning {{ border-left-color: var(--amber); }}
.dta-clause--neutral {{ border-left-color: var(--teal); }}
.dta-clause-head {{
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--s2); margin-bottom: 10px; flex-wrap: wrap;
}}
.dta-clause-title {{ font-weight: 650; color: var(--navy); font-size: 16px; }}
.dta-quote {{
  border-left: 3px solid var(--border); padding: 8px 0 8px 14px;
  margin: 10px 0; color: var(--muted); font-size: 14px;
  font-style: italic; word-break: break-word;
}}
.dta-clause-label {{
  font-size: 12px; font-weight: 650; color: var(--muted);
  text-transform: uppercase; letter-spacing: .05em; margin-top: 12px;
}}

/* ----------------------------------------------------------------- source */

.dta-source {{
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: var(--s2); margin-bottom: 10px; background: var(--surface);
}}
.dta-source--official {{ border-left: 4px solid var(--emerald); }}
.dta-source--internal {{ border-left: 4px solid var(--amber); }}
.dta-source-title {{ font-weight: 650; color: var(--navy); }}
.dta-source-meta {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}

/* ---------------------------------------------------------------- notices */

.dta-note {{
  border-radius: var(--radius-sm); padding: 14px var(--s2);
  font-size: 14px; border: 1px solid var(--border); background: var(--surface);
}}
.dta-note--info {{ background:#F2F7F8; border-color:#CFE3E6; }}
.dta-note--warning {{ background:#FDF7EC; border-color:#EEDCB6; }}
.dta-note--risk {{ background:#FDF0F0; border-color:#F2CACA; }}
.dta-note strong {{ color: var(--navy); }}

.dta-footer {{
  margin-top: var(--s6); padding-top: var(--s3);
  border-top: 1px solid var(--border);
  font-size: 13px; color: var(--muted); line-height: 1.65;
}}
.dta-footer strong {{ color: var(--text); }}

/* ------------------------------------------------------ streamlit widgets */

.stButton > button {{
  border-radius: var(--radius-sm); font-weight: 600;
  border: 1px solid var(--border); padding: .55rem 1.1rem;
  transition: none;
}}
.stButton > button[kind="primary"] {{
  background: var(--navy); border-color: var(--navy); color: #fff;
}}
/* Streamlit renders the label inside a child element that carries its own
   colour, so setting colour on the button alone leaves the text unreadable
   against the dark fill. Force the child to inherit. */
.stButton > button[kind="primary"] *,
.stDownloadButton > button[kind="primary"] * {{ color: inherit !important; }}
.stDownloadButton > button[kind="primary"] {{
  background: var(--navy); border-color: var(--navy); color: #fff;
}}
.stButton > button[kind="primary"]:hover:not(:disabled) {{
  background: #0B1F33; border-color: #0B1F33; color: #fff;
}}
/* A disabled primary button kept the dark fill, leaving the label almost
   unreadable. Mute the whole control instead so the state is obvious. */
.stButton > button:disabled *,
.stDownloadButton > button:disabled * {{ color: inherit !important; }}
.stButton > button:disabled,
.stButton > button[kind="primary"]:disabled {{
  background: #EEF1F4 !important;
  border-color: var(--border) !important;
  color: #9AA7B1 !important;
  cursor: not-allowed;
}}
.stDownloadButton > button:disabled {{
  background: #EEF1F4 !important; border-color: var(--border) !important;
  color: #9AA7B1 !important; cursor: not-allowed;
}}
.stButton > button:focus-visible,
[data-testid="stFileUploaderDropzone"]:focus-within,
.stTextArea textarea:focus-visible,
[data-baseweb="tab"]:focus-visible {{
  outline: 3px solid rgba(8,127,140,.45) !important;
  outline-offset: 2px !important;
}}

[data-testid="stFileUploaderDropzone"] {{
  background: #FAFCFD; border: 1.5px dashed #B9CBD4; border-radius: var(--radius-sm);
}}

[data-testid="stTabs"] [data-baseweb="tab-list"] {{
  gap: 2px; border-bottom: 1px solid var(--border);
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
  height: 44px; padding: 0 16px; font-weight: 600; color: var(--muted);
}}
[data-testid="stTabs"] [aria-selected="true"] {{ color: var(--navy); }}

[data-testid="stExpander"] details {{
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface);
}}

hr {{ border-color: var(--border); }}

/* ------------------------------------------------------------ responsive */

@media (max-width: 1100px) {{
  h1 {{ font-size: 36px; }}
  .dta-verdict-title {{ font-size: 26px; }}
}}
@media (max-width: 720px) {{
  html, body {{ font-size: 15px; }}
  h1 {{ font-size: 30px; }}
  h2 {{ font-size: 23px; }}
  .dta-verdict-title {{ font-size: 22px; }}
  .dta-metric-value {{ font-size: 25px; }}
  .dta-card, .dta-verdict {{ padding: var(--s2); }}
  .dta-header {{ flex-direction: column; align-items: flex-start; }}
  .dta-timeline {{ grid-template-columns: 1fr; text-align: left; }}
  .dta-timeline-span {{ min-width: 0; }}
  .dta-kv {{ grid-template-columns: 1fr; }}
  [data-testid="stTabs"] [data-baseweb="tab-list"] {{ overflow-x: auto; }}
}}

/* Nothing should force the page itself to scroll sideways. */
[data-testid="stAppViewContainer"] {{ overflow-x: hidden; }}

@media print {{
  .dta-header, .stButton, [data-testid="stFileUploader"] {{ display: none !important; }}
}}
"""


def inject() -> None:
    """Apply the stylesheet. Call once, immediately after set_page_config."""
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)
