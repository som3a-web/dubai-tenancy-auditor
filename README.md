# Dubai Tenancy Contract Auditor

**Your landlord wants to raise your rent. Is that legal?** Upload your tenancy contract and this agent
tells you the legal maximum increase under Dubai law, which clauses in your contract conflict with that
law, and what to say when you push back.

🔗 **Live demo:** **https://dubai-tenancy-auditor.streamlit.app**
🎥 **Demo video:** _(link here)_

---

## Why this exists

Dubai rent increases are capped by **Decree No. (43) of 2013**, on a sliding scale tied to how far your
current rent sits below the market benchmark for comparable units. Most tenants have never read the
decree, don't know the tiers, and accept whatever the landlord asks for. The rules are public, precise,
and entirely mechanical — which makes them a good fit for an agent that shows its work.

## What the agent does

Five distinct tool calls, each rendered live in the UI so you can watch it reason:

| # | Tool | What it does |
|---|------|--------------|
| 1 | `parse_contract` | Reads the uploaded PDF — text or scanned — and extracts annual rent, property type, bedrooms, area/community, building, contract dates, notice period |
| 2 | `lookup_benchmark` | Finds the market benchmark for that property type in that area |
| 3 | `calculate_legal_max` | Applies the Decree 43/2013 tier table to the gap between your rent and the benchmark |
| 4 | `check_clauses` | Compares contract clauses against Dubai tenancy law and flags conflicts |
| 5 | `generate_talking_points` | Turns the finding into plain-language negotiating points |

Every legal claim in the output cites its article and law number inline. When the agent can't determine
something — unreadable PDF, unknown area, missing benchmark — it says so explicitly rather than guessing.

## The legal rules

**Decree No. (43) of 2013, Article 1** sets the maximum increase by how far current rent sits below the
average rental value of comparable units:

| Current rent vs. index average | Max increase |
|---|---|
| Up to 10% below | **0%** — no increase permitted |
| 11–20% below | **5%** |
| 21–30% below | **10%** |
| 31–40% below | **15%** |
| More than 40% below | **20%** |

**Article 2** extends this to all landlords in Dubai, *including special development zones and free zones*.
**Article 3** defers the benchmark to the "Rent Index of the Emirate of Dubai" approved by RERA.

Source: [Dubai Legislation portal — Decree No. (43) of 2013](https://dlp.dubai.gov.ae/Legislation%20Reference/2013/Decree%20No.%20(43)%20of%202013%20Determining%20Rent%20Increase%20for%20Real%20Property.html)

## Known limitations — read this

**The tier calculation is exact. The benchmark is an estimate.** These are different things and the app
labels them differently.

- Since January 2025, RERA's **Smart Rental Index** computes benchmarks at the **building** level, scoring
  each building 1–5 on construction quality, finishes, location and amenities. That building-level
  classification data is **not published**, so this tool cannot reproduce it.
- What this tool uses instead is an **area × property-type × bedroom average**, derived from DLD registered
  rental contracts and committed to this repo as a dated snapshot. The snapshot date is shown in the UI.
- **Consequence:** for a specific building, our benchmark — and therefore our verdict — can differ from the
  official calculator. Decree 43's *tiers* do not change; only the number they're applied to.
- Always verify against the official Smart Rental Index via Dubai REST or dubailand.gov.ae before acting.

**One documented interpretation.** Article 1 states its bands in whole percentages — "up to ten percent",
then "eleven percent to twenty percent" — so a gap of, say, 10.5% falls in a textual gap the decree does not
address. We take the **floor** of the gap, which yields the lower permitted increase. Rationale: if we report
0% and the true answer is 5%, the tenant queries it and the landlord produces the index and nobody loses
money; if we report 5% and the true answer is 0%, the tenant pays rent they never owed. This is our reading,
not a provision of the decree, and it is labelled as such wherever it affects a verdict.

**This is guidance, not legal advice.** It is not a substitute for a lawyer or for the Rental Disputes Centre.

## Running it locally

```bash
git clone https://github.com/som3a-web/dubai-tenancy-auditor.git
cd dubai-tenancy-auditor
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then add your key
streamlit run app.py
```

You need **one** API key, either:

- **`GEMINI_API_KEY`** — free, instant, no billing, from [Google AI Studio](https://aistudio.google.com/apikey). Recommended.
- **`ANTHROPIC_API_KEY`** — from [the Claude console](https://platform.claude.com/). Requires prepaid credit.

Put it in `.streamlit/secrets.toml`, or export it as an environment variable. **Never commit it** —
`.streamlit/secrets.toml` is gitignored.

### Tests

```bash
python -m unittest discover -s tests
```

The legal engine, tool handlers and provider selection are covered. No test makes a paid API call.

## Stack

Python 3.11 · [Streamlit](https://streamlit.io) · a hand-written tool-use loop so every intermediate step
can be rendered.

**Two model providers are supported**, selected by whichever key is configured:

| Provider | Model | Cost | Notes |
|---|---|---|---|
| Google Gemini | `gemini-2.5-flash` | Free tier | Default. No billing setup; key from [AI Studio](https://aistudio.google.com/apikey) |
| Anthropic | `claude-opus-5` | Prepaid credit | Used if `ANTHROPIC_API_KEY` is set and `LLM_PROVIDER=anthropic` |

Only `src/llm.py` is provider-specific. The legal engine, the tools, the tool loop and the UI are shared,
so switching providers changes no logic that affects a verdict.

Contracts are read through the model's native PDF input, which handles both digital and scanned documents —
no separate OCR stage. That capability is why the provider choice was constrained: one of the sample
contracts is image-only, with no text layer at all.

## Cost controls

The agent loop has a hard iteration cap and a per-run token ceiling that fails loudly rather than
silently retrying. Uploaded contracts are held in memory for the duration of the request and are not
persisted.

## Built for

The Agentic AI Demo Challenge — Decoding Data Science, Dubai.

## Licence

MIT
