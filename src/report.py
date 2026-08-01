"""PDF report generation.

Everything printed here comes from the audit result. Where a value is absent it
prints "Not established" rather than an inferred figure, and any conclusion
resting on the indicative benchmark is labelled on the page it appears — a
printed report outlives the screen it came from, so the caveats have to travel
with it.
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src import audit, legal, verdict as verdict_module
from src.audit import AuditResult
from src.ui.components import aed, date_label

NAVY = colors.HexColor("#102A43")
TEAL = colors.HexColor("#087F8C")
MUTED = colors.HexColor("#5F6B76")
BORDER = colors.HexColor("#DCE3E8")
RISK = colors.HexColor("#C53030")


def audit_reference(result: AuditResult, filename: str) -> str:
    """Short deterministic reference so a report can be matched to its run."""
    seed = f"{filename}|{result.calculation.get('current_annual_rent')}|" \
           f"{result.usage.get('total_tokens')}"
    digest = hashlib.sha256(seed.encode()).hexdigest()[:8].upper()
    return f"DTA-{datetime.now(timezone.utc):%Y%m%d}-{digest}"


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle("ct", parent=base["Title"], fontSize=26, leading=31,
                                      textColor=NAVY, alignment=TA_LEFT, spaceAfter=6),
        "cover_sub": ParagraphStyle("cs", parent=base["Normal"], fontSize=12, leading=17,
                                    textColor=MUTED, alignment=TA_LEFT),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=13.5, leading=17,
                             textColor=NAVY, spaceBefore=15, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=11, leading=14,
                             textColor=NAVY, spaceBefore=9, spaceAfter=3),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=13.5),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=8, leading=11,
                                textColor=MUTED),
        "quote": ParagraphStyle("q", parent=base["Normal"], fontSize=8.5, leading=12,
                                textColor=MUTED, leftIndent=10, fontName="Helvetica-Oblique"),
    }


def _kv_table(rows: list[tuple[str, str]], st) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", st["body"]), Paragraph(v, st["body"])] for k, v in rows]
    table = Table(data, colWidths=[62 * mm, 104 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, BORDER),
    ]))
    return table


def build(result: AuditResult, filename: str, response_text: str = "") -> bytes:
    """Render the report and return the PDF bytes."""
    st = _styles()
    decision = verdict_module.classify(result.calculation, result.benchmark)
    reference = audit_reference(result, filename)
    generated = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"Tenancy Contract Analysis {reference}",
        author="Dubai Tenancy Contract Auditor",
    )
    story: list = []

    # ---------------------------------------------------------------- cover
    story += [
        Paragraph("Tenancy Contract Analysis", st["cover_title"]),
        Paragraph("Dubai rent increase and contract review", st["cover_sub"]),
        Spacer(1, 14),
        HRFlowable(width="100%", color=BORDER, thickness=1),
        Spacer(1, 14),
        _kv_table([
            ("Audit reference", reference),
            ("Analysis date", generated),
            ("Document analysed", filename),
            ("Result", decision.status_label),
            ("Benchmark verification",
             "Official registered-contract dataset" if decision.benchmark_is_official
             else "Indicative estimate — official confirmation required"),
        ], st),
        Spacer(1, 16),
        Paragraph(
            "<b>Important.</b> This report provides automated informational analysis "
            "and is not a substitute for advice from a qualified legal professional "
            "or confirmation through the relevant official authority. Figures "
            "described as estimated are derived from an indicative market benchmark "
            "and not from RERA's official Smart Rental Index.",
            st["small"],
        ),
    ]

    # ----------------------------------------------------- executive summary
    story += [
        Paragraph("Executive summary", st["h2"]),
        Paragraph(f"<b>{decision.headline}</b>", st["body"]),
        Spacer(1, 5),
        Paragraph(decision.explanation, st["body"]),
    ]
    if decision.definitive_findings:
        story += [
            Spacer(1, 7),
            Paragraph("Findings independent of market data", st["h3"]),
        ]
        for finding in decision.definitive_findings:
            story.append(Paragraph(f"• {finding}", st["body"]))

    # ------------------------------------------------------ rent comparison
    calculation = result.calculation or {}
    ceiling = calculation.get("max_lawful_annual_rent") or []
    story += [
        Paragraph("Rent comparison", st["h2"]),
        _kv_table([
            ("Current annual rent", aed(calculation.get("current_annual_rent"), "Not established")),
            ("Requested annual rent", aed(calculation.get("proposed_annual_rent"), "Not stated")),
            ("Market benchmark (estimated)",
             f"{aed(result.benchmark.get('annual_rent_low'))} – "
             f"{aed(result.benchmark.get('annual_rent_high'))}"
             if result.benchmark.get("annual_rent_low") else "Not established"),
            ("Estimated lawful ceiling",
             f"{aed(ceiling[0])} – {aed(ceiling[1])}" if ceiling and ceiling[0] != ceiling[1]
             else aed(ceiling[0]) if ceiling else "Not established"),
            ("Potential excess requested",
             aed(calculation.get("excess_over_lawful_aed"), "None identified")),
        ], st),
    ]

    # ----------------------------------------------------- contract details
    story += [Paragraph("Extracted contract details", st["h2"])]
    corrections = result.replay_meta.get("corrections", {}) if result.replay_meta else {}
    rows = []
    for key, label, value in audit.extracted_fields(result):
        shown = corrections.get(key, value)
        if key in ("annual_rent", "proposed_rent"):
            shown = aed(shown, "Not established")
        elif "start" in key or "expiry" in key or key == "notice_served":
            shown = date_label(shown, "Not established")
        elif shown in (None, ""):
            shown = "Not established"
        rows.append((label + (" (user corrected)" if key in corrections else ""), str(shown)))
    story.append(_kv_table(rows, st))

    # ------------------------------------------------------- notice period
    notice = calculation.get("notice_check") or {}
    story += [Paragraph("Notice period analysis", st["h2"])]
    if notice.get("determinable"):
        story.append(_kv_table([
            ("Notice given", f"{notice.get('days_given')} days"
             if notice.get("days_given") is not None else "Not established"),
            ("Required minimum", "90 days"),
            ("Status", "Compliant" if notice.get("compliant") else "Potential issue"),
        ], st))
        story += [Spacer(1, 5), Paragraph(notice.get("reason", ""), st["body"])]
    else:
        story.append(Paragraph(
            notice.get("reason", "The relevant dates were not found in the document."),
            st["body"]))

    # ------------------------------------------------------ flagged clauses
    story += [PageBreak(), Paragraph("Clauses reviewed", st["h2"])]
    accepted = (result.clauses or {}).get("accepted") or []
    if not accepted:
        story.append(Paragraph("No clauses were flagged for review.", st["body"]))
    for item in accepted:
        severity = {"conflicts": "High", "questionable": "Review",
                    "lawful": "No issue"}.get(item.get("severity"), "Review")
        block = [
            Paragraph(f'{item.get("short_title", "Clause")} — {severity}', st["h3"]),
        ]
        if item.get("clause_text"):
            label = ("From the contract" if item.get("is_verbatim_quote", True)
                     else "Summarised from the contract")
            block += [Paragraph(f"{label}:", st["small"]),
                      Paragraph(item["clause_text"], st["quote"])]
        block.append(Paragraph(item.get("concern", ""), st["body"]))
        if item.get("instrument"):
            block.append(Paragraph(
                f'Reference: {item["instrument"]}, Article {item.get("article", "")}',
                st["small"]))
        story.append(KeepTogether(block))
        story.append(Spacer(1, 6))

    # -------------------------------------------------- recommended actions
    story += [Paragraph("Recommended actions", st["h2"])]
    actions = [
        "Confirm the property against the official rental index before responding.",
        "Keep a written record of the notice you received and its date.",
    ]
    if calculation.get("excess_over_lawful_aed"):
        actions.insert(0, "Raise the requested amount with your landlord in writing.")
    if notice.get("determinable") and notice.get("compliant") is False:
        actions.insert(0, "Raise the timing of the notice you were served.")
    for action in actions:
        story.append(Paragraph(f"• {action}", st["body"]))

    # ------------------------------------------------------ response draft
    if response_text:
        story += [Paragraph("Draft response to landlord", st["h2"])]
        for para in response_text.split("\n\n"):
            if para.strip():
                story += [Paragraph(para.strip().replace("\n", "<br/>"), st["body"]),
                          Spacer(1, 5)]

    # ------------------------------------------------ sources and disclaimer
    story += [Paragraph("Sources and verification", st["h2"])]
    corpus_meta = legal.load_corpus().get("meta", {})
    story.append(Paragraph(
        f"Legal provisions were retrieved from the Dubai Legislation Portal on "
        f"{corpus_meta.get('verified_on', 'an unrecorded date')}. The official "
        f"Arabic text is the legally authoritative version.", st["body"]))
    provenance = legal.load_benchmarks().get("provenance", {})
    story += [Spacer(1, 5), Paragraph(
        f"Market benchmark: {provenance.get('label', 'not available')} "
        f"(confidence: {provenance.get('confidence', 'unknown')}).", st["body"])]

    story += [
        Spacer(1, 14),
        HRFlowable(width="100%", color=BORDER, thickness=1),
        Spacer(1, 8),
        Paragraph(
            "<b>Legal disclaimer.</b> This document is generated automatically and "
            "provides informational analysis only. It does not constitute legal "
            "advice and is not a determination by any authority. Confirm all figures "
            "through the official rental index and seek qualified advice before "
            "relying on this analysis in a dispute.",
            st["small"],
        ),
        Spacer(1, 6),
        Paragraph(f"Audit reference {reference} · generated {generated}", st["small"]),
    ]

    doc.build(story)
    return buffer.getvalue()
