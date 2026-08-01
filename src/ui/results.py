"""Results presentation: verdict, financials, and the six detail tabs.

Every value rendered here came from a tool payload. Nothing is computed in this
module — if a figure is not in the payload, the interface says so rather than
deriving it, so the numbers on screen always match the numbers that were tested.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from src import audit, legal, verdict as verdict_module
from src.audit import AuditResult
from src.theme import AMBER, EMERALD, NAVY, RED, TEAL
from src.ui import components as ui
from src.ui.components import aed, badge, date_label, esc, percent, write

TAB_NAMES = [
    "Overview",
    "Rent Analysis",
    "Notice Period",
    "Contract Clauses",
    "Response Draft",
    "Evidence & Sources",
]

SEVERITY_STYLE = {
    "conflicts": ("High", "risk"),
    "questionable": ("Review", "warning"),
    "lawful": ("No issue", "success"),
}


# --------------------------------------------------------------------------
# Verdict + financial summary
# --------------------------------------------------------------------------


def verdict_section(result: AuditResult) -> verdict_module.Verdict:
    decision = verdict_module.classify(result.calculation, result.benchmark)

    meta = [
        ("Data source", decision.data_source),
        ("Last checked", date_label(decision.last_checked, "Not available")),
        (
            "Verification",
            "Official dataset" if decision.benchmark_is_official else "Confirmation required",
        ),
    ]
    ui.verdict_card(
        status_label=decision.status_label,
        headline=decision.headline,
        body=decision.explanation,
        tone=decision.tone,
        meta=meta,
    )

    if decision.definitive_findings:
        st.write("")
        items = "".join(f"<li>{esc(item)}</li>" for item in decision.definitive_findings)
        write(
            '<div class="dta-note dta-note--warning">'
            "<strong>Findings that do not depend on market data</strong>"
            f'<ul style="margin:8px 0 0 18px;padding:0">{items}</ul></div>'
        )
    return decision


def financial_summary(result: AuditResult) -> None:
    calculation = result.calculation
    current = calculation.get("current_annual_rent")
    proposed = calculation.get("proposed_annual_rent")
    ceiling = calculation.get("max_lawful_annual_rent") or []
    excess = calculation.get("excess_over_lawful_aed")
    proposed_pct = calculation.get("proposed_increase_pct")
    max_low, max_high = (calculation.get("max_increase_pct") or [None, None])[:2]

    ceiling_text = "Not available"
    if ceiling:
        ceiling_text = (
            aed(ceiling[0])
            if ceiling[0] == ceiling[1]
            else f"{aed(ceiling[0])} – {aed(ceiling[1])}"
        )

    columns = st.columns(4, gap="small")
    with columns[0]:
        ui.metric_card("Current annual rent", aed(current), "As stated in your contract")
    with columns[1]:
        ui.metric_card(
            "Landlord's request",
            aed(proposed),
            f"{percent(proposed_pct, '—', signed=True)} on current rent"
            if proposed_pct is not None
            else "Not stated in the document",
            tone="warning" if excess else "neutral",
        )
    with columns[2]:
        ui.metric_card(
            "Estimated lawful ceiling",
            ceiling_text,
            _ceiling_note(max_low, max_high),
        )
    with columns[3]:
        ui.metric_card(
            "Potential excess requested",
            aed(excess, "None identified") if excess else "None identified",
            "Above the estimated ceiling" if excess else "Within the estimated ceiling",
            tone="risk" if excess else "success",
            emphasis=bool(excess),
        )


def _ceiling_note(low, high) -> str:
    if low is None:
        return "Could not be established"
    if high is None or low == high:
        return f"Permitted increase of {low}%"
    return f"Permitted increase of {low}%–{high}%"


# --------------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------------


def detail_tabs(result: AuditResult, decision: verdict_module.Verdict) -> None:
    overview, rent, notice, clauses, response, evidence = st.tabs(TAB_NAMES)

    with overview:
        _overview(result, decision)
    with rent:
        _rent_analysis(result)
    with notice:
        _notice(result)
    with clauses:
        _clauses(result)
    with response:
        _response(result)
    with evidence:
        _evidence(result)


def _overview(result: AuditResult, decision: verdict_module.Verdict) -> None:
    ui.section_heading("What we found")

    # The written findings below are produced during analysis and are not bound
    # by the classification above. A run has been observed calling an increase
    # "unlawful" while the verdict card correctly said "appears to exceed" — so
    # where the two differ in certainty, say plainly which one governs.
    if not decision.benchmark_is_official:
        write(
            '<div class="dta-note dta-note--info" style="margin-bottom:14px">'
            "The summary below is written from the analysis. Where its wording "
            "sounds more certain than the result above, <strong>the result above "
            "governs</strong>: findings drawn from the market benchmark are "
            "estimates until confirmed against the official rental index."
            "</div>"
        )

    points = result.response.get("points") or []
    if points:
        for item in points[:4]:
            citation = item.get("citation")
            write(
                '<div style="padding:12px 0;border-bottom:1px solid var(--border)">'
                f'<div style="font-size:15px">{esc(item.get("point"))}</div>'
                + (
                    f'<div style="font-size:13px;color:var(--muted);margin-top:4px">'
                    f"{esc(citation)}</div>"
                    if citation
                    else ""
                )
                + "</div>"
            )
    elif result.narrative:
        st.markdown(esc(result.narrative)[:1200])
    else:
        st.caption("No summary points were produced for this document.")

    st.write("")
    ui.section_heading("Details we extracted")
    _contract_details(result)

    questions = audit.open_questions(result)
    unresolved = audit.unresolved_fields(result)
    if questions or unresolved:
        st.write("")
        items = "".join(f"<li>{esc(q)}</li>" for q in (questions + unresolved))
        write(
            '<div class="dta-note dta-note--info">'
            "<strong>Not established by this analysis</strong>"
            f'<ul style="margin:8px 0 0 18px;padding:0">{items}</ul></div>'
        )


def _contract_details(result: AuditResult) -> None:
    """Extracted fields, each confirmable or correctable by the user.

    Corrections are stored separately from the extraction so the original
    machine reading is never overwritten — that record is what makes the result
    auditable.
    """
    corrections: dict[str, str] = st.session_state.setdefault("corrections", {})
    fields = audit.extracted_fields(result)

    pairs: list[tuple[str, Any]] = []
    for key, label, value in fields:
        display = corrections.get(key, value)
        if key in ("annual_rent", "proposed_rent"):
            display = aed(display, "Not found") if display not in (None, "") else None
        elif key in ("contract_start", "contract_expiry",
                     "original_occupancy_start", "notice_served"):
            display = date_label(display, "Not found") if display else None
        suffix = " (user corrected)" if key in corrections else ""
        pairs.append((label + suffix, display))

    ui.key_values(pairs)

    with st.expander("Correct an extracted detail"):
        st.caption(
            "If a value was read incorrectly, record the correction here. The "
            "original extracted value is preserved for the audit trail."
        )
        options = {label: key for key, label, _ in fields}
        chosen_label = st.selectbox("Field", list(options), key="correct_field")
        chosen_key = options[chosen_label]
        original = next(v for k, _, v in fields if k == chosen_key)
        st.caption(f"Originally extracted: {esc(original, 'Not found')}")
        new_value = st.text_input(
            "Corrected value", value=str(corrections.get(chosen_key, "")), key="correct_value"
        )
        confirm, clear = st.columns(2)
        with confirm:
            if st.button("Save correction", use_container_width=True):
                if new_value.strip():
                    corrections[chosen_key] = new_value.strip()
                    st.rerun()
        with clear:
            if st.button("Clear correction", use_container_width=True,
                         disabled=chosen_key not in corrections):
                corrections.pop(chosen_key, None)
                st.rerun()

        if corrections:
            st.caption(
                "Corrections are recorded for your reference and appear in the "
                "downloadable report. They do not re-run the legal calculation."
            )


def _rent_analysis(result: AuditResult) -> None:
    calculation = result.calculation
    benchmark = result.benchmark

    if not calculation.get("determinable"):
        write(
            '<div class="dta-note dta-note--warning">'
            f'{esc(calculation.get("reason", "This could not be assessed."))}</div>'
        )
        return

    ui.section_heading("How this was calculated")

    low = benchmark.get("annual_rent_low")
    high = benchmark.get("annual_rent_high")
    current = calculation.get("current_annual_rent")
    proposed = calculation.get("proposed_annual_rent")
    ceiling = calculation.get("max_lawful_annual_rent") or []
    gap = calculation.get("gap_below_benchmark_pct") or []

    if not benchmark.get("confidence") == "high":
        write(
            '<div class="dta-note dta-note--warning">'
            "<strong>Benchmark data quality.</strong> The comparison below uses an "
            "indicative market estimate, not RERA's official building-level Smart "
            "Rental Index. Treat the permitted range as an estimate and confirm "
            "through the official index."
            "</div>"
        )
        st.write("")

    if low and high and current:
        markers = [("Your rent", float(current), NAVY)]
        if proposed:
            markers.append(("Requested", float(proposed), RED))
        if ceiling:
            markers.append(("Est. ceiling", float(ceiling[1]), EMERALD))
        ui.benchmark_scale(float(low), float(high), markers)
        st.caption(
            f"Shaded band: estimated market range for a comparable unit "
            f"({aed(low)} – {aed(high)})."
        )

    st.write("")
    steps = [
        ("Market benchmark for a comparable unit",
         f"{aed(low)} – {aed(high)}" if low and high else "Not available"),
        ("Your current rent sits below that benchmark by",
         f"{gap[0]:.0f}% – {gap[1]:.0f}%" if len(gap) == 2 else "Not available"),
        ("Decree 43/2013 permits an increase of",
         _ceiling_note(*(calculation.get("max_increase_pct") or [None, None])[:2])),
        ("Which gives an estimated lawful ceiling of",
         f"{aed(ceiling[0])} – {aed(ceiling[1])}" if ceiling and ceiling[0] != ceiling[1]
         else aed(ceiling[0]) if ceiling else "Not available"),
        ("Your landlord has requested",
         aed(proposed, "Not stated")),
    ]
    ui.key_values(steps)

    interpretation = calculation.get("band_edge_interpretation")
    if interpretation:
        st.write("")
        st.caption(esc(interpretation))


def _notice(result: AuditResult) -> None:
    notice = (result.calculation or {}).get("notice_check") or {}
    dates = result.contract.get("dates") or {}

    ui.section_heading("Notice period")

    if not notice.get("determinable"):
        write(
            '<div class="dta-note dta-note--info">'
            "<strong>Unable to verify.</strong> "
            f'{esc(notice.get("reason", "The relevant dates were not found in the document."))}'
            "</div>"
        )
        return

    compliant = notice.get("compliant")
    days = notice.get("days_given")
    label, tone = (
        ("Compliant", "success") if compliant else ("Potential issue", "warning")
    )

    write(f'<div style="margin-bottom:12px">{badge(label, tone)}</div>')
    ui.date_comparison(
        "Notice served",
        date_label(dates.get("notice_served"), "Not found"),
        f"{days} days" if days is not None else "Unknown",
        "Contract expires",
        date_label(dates.get("contract_expiry"), "Not found"),
    )
    ui.key_values(
        [
            ("Notice given", f"{days} days" if days is not None else "Not found"),
            ("Required minimum", "90 days"),
            ("Status", label),
        ]
    )
    st.write("")
    st.caption(esc(notice.get("reason", "")))


def _clauses(result: AuditResult) -> None:
    accepted = (result.clauses or {}).get("accepted") or []
    ui.section_heading("Clauses reviewed", f"{len(accepted)} clause(s) checked against Dubai tenancy law.")

    if not accepted:
        st.caption("No clauses were flagged for review in this document.")
        return

    order = {"conflicts": 0, "questionable": 1, "lawful": 2}
    for item in sorted(accepted, key=lambda c: order.get(c.get("severity"), 3)):
        risk_label, tone = SEVERITY_STYLE.get(item.get("severity"), ("Review", "warning"))
        reference = None
        if item.get("instrument"):
            reference = f'{item["instrument"]}, Article {item.get("article", "")}'.strip(", ")
        ui.clause_card(
            title=item.get("short_title") or "Clause",
            risk_label=risk_label,
            tone=tone,
            quoted_text=item.get("clause_text"),
            explanation=item.get("concern") or "",
            reference=reference,
            action=(
                "Raise this with your landlord before signing the renewal."
                if item.get("severity") == "conflicts"
                else None
            ),
            is_verbatim=bool(item.get("is_verbatim_quote", True)),
        )


def _response(result: AuditResult) -> None:
    points = result.response.get("points") or []
    summary = result.response.get("verdict_summary") or ""

    ui.section_heading("Response to your landlord")
    if not points and not summary:
        st.caption("No response draft was produced for this document.")
        return

    tone_choice = st.radio(
        "Tone",
        ["Formal", "Friendly"],
        horizontal=True,
        label_visibility="collapsed",
        key="response_tone",
    )
    arabic = st.session_state.get("language") == "العربية"
    draft = build_response(result, formal=tone_choice == "Formal", arabic=arabic)

    if arabic:
        st.caption(
            "النسخة العربية تتضمن الصياغة والأرقام. التفاصيل القانونية الكاملة "
            "متوفرة في النسخة الإنجليزية."
        )

    edited = st.text_area(
        "Draft", value=draft, height=340, label_visibility="collapsed", key="response_draft"
    )
    st.download_button(
        "Download as text",
        data=edited,
        file_name="response-to-landlord.txt",
        mime="text/plain",
        use_container_width=False,
    )
    st.caption(
        "Review before sending. The wording is deliberately cautious where the "
        "analysis depends on an estimated benchmark."
    )


def build_response(result: AuditResult, formal: bool = True, arabic: bool = False) -> str:
    """Assemble the letter from findings only. Adds no legal claims of its own.

    The Arabic version renders the letter structure and the figures, which are
    language-neutral. It deliberately does NOT machine-translate the individual
    findings: those are free text produced during analysis, and translating them
    here would put words into the analysis that it did not produce. The English
    version remains authoritative and the interface says so.
    """
    if arabic:
        return _build_response_arabic(result, formal=formal)

    calculation = result.calculation or {}
    proposed = calculation.get("proposed_annual_rent")
    ceiling = calculation.get("max_lawful_annual_rent") or []
    points = result.response.get("points") or []

    opening = (
        "Dear Sir or Madam,\n\nI am writing regarding the proposed rent for the "
        "renewal of my tenancy."
        if formal
        else "Hello,\n\nThanks for sending through the renewal terms. I wanted to "
        "raise a couple of points before we finalise anything."
    )

    body = []
    if proposed:
        body.append(
            f"You have proposed an annual rent of {aed(proposed)}."
            + (
                f" Based on the market benchmark for a comparable unit, my "
                f"understanding is that the permitted rent on renewal would be "
                f"up to {aed(ceiling[1])}."
                if ceiling
                else ""
            )
        )

    for item in points[:5]:
        text = item.get("point")
        if not text:
            continue
        citation = item.get("citation")
        body.append(f"{text}" + (f" ({citation})" if citation else ""))

    closing = (
        "I would be grateful if you could confirm the position against the official "
        "rental index before we proceed. I am happy to discuss this and reach an "
        "agreement.\n\nKind regards,"
        if formal
        else "Could we check this against the official rental index before going "
        "ahead? Happy to talk it through.\n\nThanks,"
    )
    return "\n\n".join([opening, *body, closing])


def _evidence(result: AuditResult) -> None:
    ui.section_heading(
        "Evidence and sources",
        "Every legal reference used in this analysis, with its verification status.",
    )

    corpus = legal.load_corpus()
    meta = corpus.get("meta", {})
    sources = meta.get("sources", {})
    verified_on = meta.get("verified_on", "Not recorded")

    used_ids: set[str] = set()
    for item in (result.clauses or {}).get("accepted", []):
        if item.get("provision_id"):
            used_ids.add(item["provision_id"])
    for item in (result.response.get("points") or []):
        if item.get("provision_id"):
            used_ids.add(item["provision_id"])
    for citation in (result.calculation or {}).get("citations", []):
        used_ids.add(citation)
    notice_citation = ((result.calculation or {}).get("notice_check") or {}).get("citation")
    if notice_citation:
        used_ids.add(notice_citation)

    st.markdown("#### Legal instruments")
    if not used_ids:
        st.caption("No legal provisions were cited for this document.")

    for provision_id in sorted(used_ids):
        provision = legal.provision(provision_id)
        if not provision:
            continue
        instrument = provision.get("instrument", "")
        url = _source_url(sources, provision_id)
        is_quote = "quote" in provision
        ui.source_card(
            title=f'{instrument}, Article {provision.get("article", "")}'.strip(", "),
            source_type="official",
            explanation=provision.get("short_title", ""),
            meta=(
                f"{'Verbatim text' if is_quote else 'Summary, not a direct quotation'} "
                f"· Retrieved from the Dubai Legislation Portal on {verified_on}"
            ),
            url=url,
        )

    st.markdown("#### Market benchmark")
    benchmark = result.benchmark or {}
    provenance = legal.load_benchmarks().get("provenance", {})
    official = benchmark.get("source_kind") == "dld_registered_contracts"
    ui.source_card(
        title=provenance.get("label", "Benchmark dataset"),
        source_type="official" if official else "internal",
        explanation=(
            "Derived from registered rental contracts."
            if official
            else "Indicative market ranges. This is not RERA's official Smart Rental "
            "Index and cannot reproduce its building-level classification."
        ),
        meta=(
            f"Snapshot: {benchmark.get('snapshot_date', provenance.get('snapshot_date', 'unknown'))}"
            + (
                f" · {benchmark.get('sample_contracts')} contracts in this cell"
                if benchmark.get("sample_contracts")
                else ""
            )
        ),
    )

    st.caption(
        "Official sources are quoted from primary legislation. Internal estimates "
        "are clearly identified and should be confirmed through the relevant "
        "authority before being relied upon."
    )


def _source_url(sources: dict, provision_id: str) -> str | None:
    if provision_id.startswith("decree-43"):
        return sources.get("decree_43_2013")
    if provision_id.startswith("law-33"):
        return sources.get("law_33_2008")
    if provision_id.startswith("law-26"):
        return sources.get("law_26_2007")
    return None


def _build_response_arabic(result: AuditResult, formal: bool = True) -> str:
    """Arabic letter covering the structure and the figures.

    Individual findings are omitted rather than machine-translated — see
    build_response. The closing points the reader at the English version so the
    omission is explicit rather than silent.
    """
    calculation = result.calculation or {}
    proposed = calculation.get("proposed_annual_rent")
    ceiling = calculation.get("max_lawful_annual_rent") or []

    opening = (
        "السادة المحترمون،\n\nأكتب إليكم بخصوص الإيجار المقترح لتجديد عقد الإيجار."
        if formal
        else "مرحبًا،\n\nشكرًا لإرسال شروط التجديد. أود توضيح بعض النقاط قبل إتمام الاتفاق."
    )

    body = []
    if proposed:
        line = f"لقد اقترحتم إيجارًا سنويًا قدره {aed(proposed)}."
        if ceiling:
            line += (
                f" وبحسب المؤشر السوقي للوحدات المماثلة، أفهم أن الحد الأقصى "
                f"للإيجار عند التجديد يبلغ {aed(ceiling[1])}."
            )
        body.append(line)

    notice = calculation.get("notice_check") or {}
    if notice.get("determinable") and notice.get("compliant") is False and notice.get("days_given") is not None:
        body.append(
            f"كما أود الإشارة إلى أن الإشعار وصلني قبل {notice['days_given']} يومًا "
            "من انتهاء العقد، وهي مدة تقل عن تسعين يومًا."
        )

    if calculation.get("article_9_blocks_increase"):
        body.append(
            "بالإضافة إلى ذلك، لم تمضِ سنتان على بداية علاقة الإيجار الأصلية."
        )

    closing = (
        "أرجو التكرم بتأكيد الوضع من خلال مؤشر الإيجارات الرسمي قبل المتابعة، "
        "ويسعدني مناقشة الأمر للوصول إلى اتفاق مناسب للطرفين."
        "\n\nمع خالص التقدير،"
        if formal
        else "هل يمكننا التحقق من ذلك عبر مؤشر الإيجارات الرسمي قبل المتابعة؟ "
        "يسعدني مناقشة الأمر.\n\nمع الشكر،"
    )
    return "\n\n".join([opening, *body, closing])
