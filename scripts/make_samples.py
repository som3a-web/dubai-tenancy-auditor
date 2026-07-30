#!/usr/bin/env python3
"""Generate the demo tenancy contracts in samples/.

    python scripts/make_samples.py

Three fixtures, each exercising a different path through the agent:

  1. Dubai Marina 1 B/R  — landlord demands 15%; rent sits ABOVE the benchmark
                            band, so the lawful maximum is 0%. The headline case.
  2. JVC studio          — tenancy is 15 months old, so Article 9 of Law 26/2007
                            blocks any increase outright, overriding the tier
                            table. Tests that the override beats the arithmetic.
  3. Deira 2 B/R         — image-only PDF (no text layer at all) with notice
                            served 76 days before expiry, breaching the 90-day
                            requirement in Article 14. Tests the vision path and
                            the notice check together.

Every contract also carries four clauses that conflict with Dubai tenancy law,
plus one that LOOKS unfair but is actually the statutory default (tenant pays
government fees, Article 22). That last one is a negative control: an agent that
flags it is over-flagging, and the integration test asserts it is not flagged.

All parties, ID numbers and premises are invented. No real personal data.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "samples"

ACCENT = colors.HexColor("#0B7A6B")
RULE = colors.HexColor("#9AA5A2")


@dataclass
class Contract:
    filename: str
    scanned: bool

    ejari_no: str
    landlord: str
    landlord_id: str
    tenant: str
    tenant_id: str

    community: str
    building: str
    unit: str
    property_type: str
    bedrooms: str
    plot_no: str
    dewa_no: str
    makani_no: str

    annual_rent: int
    proposed_rent: int
    contract_from: str
    contract_to: str
    original_start: str
    notice_served: str
    payments: str
    deposit: str

    clauses: list[str] = field(default_factory=list)
    demo_note: str = ""


# --------------------------------------------------------------------------
# Clause pools. The first four conflict with the corpus; the fifth does not.
# --------------------------------------------------------------------------

CLAUSE_DEPOSIT_NON_REFUNDABLE = (
    "The security deposit paid by the Tenant shall be treated as a "
    "non-refundable administration charge and shall under no circumstances be "
    "returned to the Tenant upon expiry of this Contract."
)
CLAUSE_ALL_MAINTENANCE_ON_TENANT = (
    "The Tenant shall bear the full cost of all maintenance and repair of the "
    "Premises without exception, including structural, mechanical and "
    "air-conditioning works, and including any defect existing prior to the "
    "commencement of this Contract."
)
CLAUSE_AS_NEW_CONDITION = (
    "Upon expiry the Tenant shall return the Premises in as-new condition. Any "
    "wear to paint, flooring or fittings, however ordinary, shall be made good "
    "at the Tenant's sole expense."
)
CLAUSE_LANDLORD_MAY_TERMINATE = (
    "The Landlord reserves the right to terminate this Contract at any time by "
    "giving the Tenant thirty (30) days written notice, without assigning any "
    "reason, and the Tenant shall vacate the Premises accordingly."
)
CLAUSE_TENANT_PAYS_GOVT_FEES = (
    "The Tenant shall be responsible for all government fees, municipality "
    "charges and utility registration costs arising from occupation of the "
    "Premises."
)
CLAUSE_RENT_INCREASE_AT_DISCRETION = (
    "The Landlord may revise the Annual Rent upon renewal at the Landlord's "
    "sole discretion, and the Tenant hereby waives any right to object to such "
    "revision before any tribunal or committee."
)

STANDARD_BAD_CLAUSES = [
    CLAUSE_DEPOSIT_NON_REFUNDABLE,
    CLAUSE_ALL_MAINTENANCE_ON_TENANT,
    CLAUSE_AS_NEW_CONDITION,
    CLAUSE_LANDLORD_MAY_TERMINATE,
    CLAUSE_TENANT_PAYS_GOVT_FEES,  # negative control - lawful under Article 22
]


CONTRACTS = [
    Contract(
        filename="sample_1_marina_1br.pdf",
        scanned=False,
        ejari_no="EJ-2026-0417739",
        landlord="Gulf Crest Properties LLC",
        landlord_id="Trade Licence 000000-DEMO",
        tenant="A. Demo Tenant",
        tenant_id="784-0000-0000000-0 (redacted)",
        community="Dubai Marina",
        building="Marina Sapphire Tower",
        unit="1104",
        property_type="Residential Apartment",
        bedrooms="1 B/R",
        plot_no="MAR-0000-DEMO",
        dewa_no="0000000000",
        makani_no="0000 00000",
        annual_rent=117_000,
        proposed_rent=134_550,
        contract_from="01/09/2025",
        contract_to="31/08/2026",
        original_start="01/09/2023",
        notice_served="15/05/2026",
        payments="Four (4) cheques of AED 29,250 each",
        deposit="AED 5,850 (5% of Annual Rent)",
        clauses=STANDARD_BAD_CLAUSES + [CLAUSE_RENT_INCREASE_AT_DISCRETION],
        demo_note=(
            "Headline case. Landlord demands +15%. Rent sits at/above the "
            "benchmark band, so the lawful maximum is 0%. Notice was served "
            "108 days before expiry, so the notice itself is compliant - the "
            "problem is the amount, not the timing."
        ),
    ),
    Contract(
        filename="sample_2_jvc_studio.pdf",
        scanned=False,
        ejari_no="EJ-2026-0518824",
        landlord="Hessa Holdings FZ-LLC",
        landlord_id="Trade Licence 000000-DEMO",
        tenant="B. Demo Tenant",
        tenant_id="784-0000-0000000-0 (redacted)",
        community="Jumeirah Village Circle",
        building="Diamond Views IV",
        unit="G-07",
        property_type="Residential Studio",
        bedrooms="Studio",
        plot_no="JVC-0000-DEMO",
        dewa_no="0000000000",
        makani_no="0000 00000",
        annual_rent=42_000,
        proposed_rent=46_200,
        contract_from="01/09/2025",
        contract_to="31/08/2026",
        original_start="01/06/2025",
        notice_served="20/04/2026",
        payments="Two (2) cheques of AED 21,000 each",
        deposit="AED 2,100 (5% of Annual Rent)",
        clauses=STANDARD_BAD_CLAUSES,
        demo_note=(
            "Article 9 override. The original tenancy began 01/06/2025, so the "
            "two-year freeze runs to 01/06/2027. No increase is lawful on this "
            "renewal whatever the index says - the override must beat the tier "
            "calculation."
        ),
    ),
    Contract(
        filename="sample_3_deira_2br_scanned.pdf",
        scanned=True,
        ejari_no="EJ-2026-0332015",
        landlord="Al Ras Real Estate Est.",
        landlord_id="Trade Licence 000000-DEMO",
        tenant="C. Demo Tenant",
        tenant_id="784-0000-0000000-0 (redacted)",
        community="Deira",
        building="Al Muteena Plaza",
        unit="502",
        property_type="Residential Apartment",
        bedrooms="2 B/R",
        plot_no="DEI-0000-DEMO",
        dewa_no="0000000000",
        makani_no="0000 00000",
        annual_rent=68_000,
        proposed_rent=81_600,
        contract_from="16/09/2025",
        contract_to="15/09/2026",
        original_start="16/09/2021",
        notice_served="01/07/2026",
        payments="Six (6) cheques of AED 11,333 each",
        deposit="AED 3,400 (5% of Annual Rent)",
        clauses=STANDARD_BAD_CLAUSES,
        demo_note=(
            "Vision path plus notice defect. Image-only PDF with no text layer. "
            "Notice served 01/07/2026 for a 15/09/2026 expiry is 76 days - "
            "short of the 90 days Article 14 requires, so the increase fails "
            "for this renewal and Article 6 renews on the same terms."
        ),
    ),
]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "T", parent=base["Title"], fontSize=15, leading=19,
            textColor=colors.HexColor("#16211F"), spaceAfter=2,
        ),
        "sub": ParagraphStyle(
            "S", parent=base["Normal"], fontSize=8.5, leading=11,
            alignment=1, textColor=RULE,
        ),
        "h": ParagraphStyle(
            "H", parent=base["Heading2"], fontSize=10, leading=13,
            textColor=ACCENT, spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "B", parent=base["Normal"], fontSize=8.5, leading=11.5,
        ),
        "cell": ParagraphStyle(
            "C", parent=base["Normal"], fontSize=8.5, leading=11,
        ),
        "clause": ParagraphStyle(
            "L", parent=base["Normal"], fontSize=8.5, leading=11.5,
            spaceAfter=5, leftIndent=12, firstLineIndent=-12,
        ),
        "small": ParagraphStyle(
            "M", parent=base["Normal"], fontSize=7.5, leading=10,
            textColor=RULE,
        ),
    }


def _kv_table(rows: list[tuple[str, str]], st) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", st["cell"]), Paragraph(v, st["cell"])] for k, v in rows]
    table = Table(data, colWidths=[52 * mm, 110 * mm])
    table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#E3E7E6")),
        ])
    )
    return table


def build_story(c: Contract, st) -> list:
    story: list = [
        Paragraph("UNIFIED TENANCY CONTRACT", st["title"]),
        Paragraph(
            "Government of Dubai &nbsp;·&nbsp; Land Department &nbsp;·&nbsp; "
            "Real Estate Regulatory Agency &nbsp;·&nbsp; Ejari",
            st["sub"],
        ),
        Spacer(1, 4),
        Paragraph(
            "<b>SPECIMEN — SYNTHETIC DATA.</b> Generated for testing the Dubai "
            "Tenancy Contract Auditor. All parties, identification numbers and "
            "premises are fictitious. This is not a real tenancy contract and "
            "has no legal effect.",
            st["small"],
        ),
        Spacer(1, 8),
        Paragraph(f"Ejari Contract No. {c.ejari_no}", st["body"]),
    ]

    story += [Paragraph("1. Parties", st["h"])]
    story += [_kv_table([
        ("Landlord", c.landlord),
        ("Landlord Licence / ID", c.landlord_id),
        ("Tenant", c.tenant),
        ("Tenant Emirates ID", c.tenant_id),
    ], st)]

    story += [Paragraph("2. Premises", st["h"])]
    story += [_kv_table([
        ("Property Type", c.property_type),
        ("Size", c.bedrooms),
        ("Building Name", c.building),
        ("Unit / Flat No.", c.unit),
        ("Area / Community", c.community),
        ("Plot No.", c.plot_no),
        ("DEWA Premises No.", c.dewa_no),
        ("Makani No.", c.makani_no),
    ], st)]

    story += [Paragraph("3. Term and Rent", st["h"])]
    story += [_kv_table([
        ("Contract Period From", c.contract_from),
        ("Contract Period To", c.contract_to),
        ("Date Tenant First Occupied Premises", c.original_start),
        ("Annual Rent (current term)", f"AED {c.annual_rent:,} ({_words(c.annual_rent)})"),
        ("Mode of Payment", c.payments),
        ("Security Deposit", c.deposit),
    ], st)]

    story += [Paragraph("4. Renewal Notice", st["h"])]
    story += [_kv_table([
        ("Notice of Amendment Served On", c.notice_served),
        ("Proposed Annual Rent on Renewal", f"AED {c.proposed_rent:,}"),
        ("Proposed Increase", f"{_pct(c.annual_rent, c.proposed_rent)}"),
        ("Method of Service", "Delivered by hand / email to the Tenant"),
    ], st)]

    story += [Paragraph("5. Terms and Conditions", st["h"])]
    for i, clause in enumerate(c.clauses, start=1):
        story.append(Paragraph(f"5.{i}&nbsp;&nbsp;{clause}", st["clause"]))

    sig = Table(
        [[
            Paragraph("<b>Landlord</b><br/><br/><br/>__________________________<br/>Signature &amp; Date", st["cell"]),
            Paragraph("<b>Tenant</b><br/><br/><br/>__________________________<br/>Signature &amp; Date", st["cell"]),
        ]],
        colWidths=[81 * mm, 81 * mm],
    )
    sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 14)]))
    story.append(KeepTogether([Spacer(1, 10), sig]))
    return story


def _pct(current: int, proposed: int) -> str:
    return f"{(proposed - current) / current * 100:.0f}%"


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]


def _words(amount: int) -> str:
    """Rough amount-in-words, as Ejari contracts require rent in figures and words."""
    thousands = amount // 1000
    remainder = amount % 1000
    parts = []
    if thousands >= 100:
        parts.append(f"{_ONES[thousands // 100]} Hundred")
        thousands %= 100
    if thousands:
        parts.append(f"{thousands}")
    text = " ".join(parts) + " Thousand" if parts else "Zero"
    if remainder:
        text += f" {remainder}"
    return f"{text} UAE Dirhams only"


def render_text_pdf(c: Contract, path: Path) -> None:
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Unified Tenancy Contract {c.ejari_no}",
        author="Dubai Tenancy Contract Auditor - synthetic sample",
    )
    doc.build(build_story(c, _styles()))


def render_scanned_pdf(c: Contract, path: Path) -> None:
    """Render, rasterise, degrade, and re-embed as images.

    The result has NO text layer, so pdf text extraction returns nothing and the
    model must actually read the pixels. That is the point of this fixture: a
    text-layer PDF dressed up to look scanned would not test the vision path.
    """
    import pypdfium2 as pdfium
    from PIL import Image, ImageEnhance, ImageFilter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdfcanvas

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
    )
    doc.build(build_story(c, _styles()))
    buffer.seek(0)

    pdf = pdfium.PdfDocument(buffer.read())
    out = pdfcanvas.Canvas(str(path), pagesize=A4)
    page_w, page_h = A4

    for index in range(len(pdf)):
        bitmap = pdf[index].render(scale=200 / 72)
        image = bitmap.to_pil().convert("L")

        # Make it look like a photocopy: slight skew, softening, contrast loss,
        # and a faint grey cast.
        image = image.rotate(-0.45, resample=Image.BICUBIC, expand=False, fillcolor=245)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.45))
        image = ImageEnhance.Contrast(image).enhance(0.88)
        image = ImageEnhance.Brightness(image).enhance(0.97)

        tmp = io.BytesIO()
        image.save(tmp, format="JPEG", quality=62)
        tmp.seek(0)
        out.drawImage(ImageReader(tmp), 0, 0, width=page_w, height=page_h)
        out.showPage()

    out.save()
    pdf.close()


def main() -> int:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    manifest = ["# Demo contracts", "", "Generated by `scripts/make_samples.py`.",
                "All data synthetic. These are the only contracts used in the",
                "recorded demo — never type live.", ""]

    for c in CONTRACTS:
        path = SAMPLES_DIR / c.filename
        if c.scanned:
            render_scanned_pdf(c, path)
        else:
            render_text_pdf(c, path)
        kind = "image-only (no text layer)" if c.scanned else "text layer"
        size_kb = path.stat().st_size / 1024
        print(f"  {c.filename}  [{kind}, {size_kb:.0f} KB]")

        manifest += [
            f"## {c.filename}",
            "",
            f"- **Property:** {c.bedrooms} in {c.community} ({c.building}, unit {c.unit})",
            f"- **Current rent:** AED {c.annual_rent:,}",
            f"- **Landlord demands:** AED {c.proposed_rent:,} "
            f"({_pct(c.annual_rent, c.proposed_rent)})",
            f"- **Original occupancy from:** {c.original_start}",
            f"- **Term:** {c.contract_from} to {c.contract_to}",
            f"- **Notice served:** {c.notice_served}",
            f"- **PDF kind:** {kind}",
            "",
            f"{c.demo_note}",
            "",
        ]

    (SAMPLES_DIR / "README.md").write_text("\n".join(manifest) + "\n")
    print(f"\nWrote {len(CONTRACTS)} contracts + manifest to {SAMPLES_DIR.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
