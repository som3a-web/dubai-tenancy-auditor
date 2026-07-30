# Submission draft

Copy from here into the nas.com submission form. Adjust to whatever fields it
actually asks for — this covers the usual ones.

---

## Project name

**Dubai Tenancy Contract Auditor**

## One-line description

An agent that reads your tenancy contract and tells you whether your landlord's
rent increase is actually legal under Dubai law — and what to say about it.

## Links

- **Live demo:** https://dubai-tenancy-auditor.streamlit.app
- **Source:** https://github.com/som3a-web/dubai-tenancy-auditor
- **Demo video:** _(add link)_

## Full description

Dubai caps rent increases. Decree No. 43 of 2013 sets a sliding scale based on
how far your current rent sits below the market average for comparable units —
0%, 5%, 10%, 15% or 20%, and nothing above that is lawful. The rules are public
and entirely mechanical. Almost no tenant reads them, so people pay what they're
asked.

This tool takes a tenancy contract PDF and runs a five-step agentic loop:

1. **Reads the contract** — rent, area, unit size, contract dates, notice date.
   Works on scanned contracts as well as digital ones.
2. **Finds the market benchmark** for that area and unit size.
3. **Applies the law** — the Decree 43 tier table, plus two rules that decide
   most real cases: Article 9 of Law 26/2007, which bars *any* increase within
   two years of the original tenancy starting, and Article 14 (as replaced by
   Law 33/2008), which requires 90 days' notice to change any term.
4. **Checks every clause** against Dubai tenancy law.
5. **Drafts the negotiating points** in plain language.

Every step is rendered live in the interface — the tool called, what went in,
what came back — so you can watch the reasoning rather than trust a number.

### What we did differently

**The agent does no arithmetic and cannot invent a law.** Both are structural,
not prompt instructions.

Every figure in a verdict comes from a tested Python engine, not the model. The
tier table, the two-year freeze and the notice calculation are covered by 103
tests, so a wrong verdict is a failing test rather than a bad sample.

Citations are verified rather than trusted. The model cites a provision by ID;
the tool resolves that ID against a corpus of statute text pulled verbatim from
the Dubai Legislation Portal and returns the real wording. An ID that doesn't
exist is rejected. The model therefore cannot fabricate a provision — the worst
it can do is fail to cite one.

**It says when it can't tell you.** Unknown area, unreadable field, missing
date — each produces an explicit "I can't determine this because X". We took
that seriously because the failure mode here isn't inconvenience: a confident
wrong answer about someone's housing costs them money they didn't owe.

### Stated limitations

Since January 2025 RERA's Smart Rental Index computes benchmarks at the
*building* level, scoring each building 1–5. That classification isn't
published, so this tool can't reproduce it. It uses an area-level estimate and
labels it as such throughout, reporting a range rather than a single figure when
confidence is low. The tier calculation is exact; the benchmark is an estimate,
and the interface never blurs the two.

## Tech

Python 3.11, Streamlit, Google Gemini (free tier) with a hand-written tool-use
loop so every intermediate step can be rendered. The provider is pluggable —
Anthropic Claude is also supported — and only the conversation plumbing is
provider-specific, so nothing affecting a verdict changes with the model.

Contracts are read through the model's native PDF input, handling scanned
documents without a separate OCR stage.

## Category fit

- **Functionality** — complete five-tool loop, working live URL, three worked
  examples covering different parts of the law.
- **Problem value** — every renter in Dubai faces this annually.
- **Technical implementation** — verified-citation architecture, tested legal
  engine, provider abstraction, recorded-run fallback.
- **Originality** — no existing open-source tool audits Dubai tenancy contracts
  against the decree.
- **Demo clarity** — the agent shows its work; the verdict is readable in five
  seconds.
- **Audience relevance** — Dubai tenancy law, Dubai judges, a problem the room
  has personally negotiated.

## Not legal advice

The tool states this in the interface and so do we. It's guidance, and it points
users to the official Smart Rental Index and the Rental Disputes Centre.
