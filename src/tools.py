"""Tool schemas and handlers for the audit agent.

Two rules shape everything here.

1. **The model does no arithmetic and no law.** Every number in a verdict comes
   from src.legal. Tools that look like they compute things are thin wrappers.
2. **Citations are verified, not trusted.** The model cites a provision by id;
   the handler looks the id up in data/legal_corpus.json and returns the
   verbatim text. An id that does not exist is rejected with an error the model
   must act on. The model therefore cannot invent a provision even if it wants
   to — the worst it can do is fail to cite one.

`parse_contract` is deliberately shaped so the model's extraction arrives AS the
tool input under a strict schema, rather than as prose it later refers to. That
makes the reading step inspectable, type-checked, and renderable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from src import legal

# --------------------------------------------------------------------------
# Date parsing
# --------------------------------------------------------------------------

_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y")


def parse_date(raw: str | None) -> date | None:
    """Parse a contract date. Dubai contracts are DD/MM/YYYY; try that first."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_money(raw: Any) -> float | None:
    """Parse an AED amount, tolerating separators and a currency prefix."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    text = re.sub(r"(?i)\b(aed|dhs?|dirhams?)\b", "", str(raw))
    text = re.sub(r"[,\s]", "", text).strip()
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    value = float(match.group())
    return value if value > 0 else None


def normalise_size(raw: str | None) -> str | None:
    """Map a contract's size field onto studio/1br/2br/3br."""
    if not raw:
        return None
    text = str(raw).strip().lower()
    if "studio" in text:
        return "studio"
    match = re.search(r"\b([0-9])\b", text)
    if match:
        return {"0": "studio", "1": "1br", "2": "2br", "3": "3br"}.get(match.group(1))
    for word, key in (("one", "1br"), ("two", "2br"), ("three", "3br")):
        if word in text:
            return key
    return None


# --------------------------------------------------------------------------
# Tool schemas
# --------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "parse_contract",
        "description": (
            "Record the fields you have read from the tenancy contract. Call this "
            "first, exactly once. Report only what the document actually shows: "
            "use null for any field you cannot read, and never infer a value from "
            "another field. If the document is not a Dubai tenancy contract, say "
            "so in document_notes and set the fields you cannot find to null."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "annual_rent": {
                    "type": ["string", "null"],
                    "description": "Current annual rent exactly as printed, e.g. 'AED 117,000'.",
                },
                "proposed_rent": {
                    "type": ["string", "null"],
                    "description": "Rent the landlord proposes on renewal, if the document states one.",
                },
                "area": {
                    "type": ["string", "null"],
                    "description": "Area or community, e.g. 'Dubai Marina'. Not the building name.",
                },
                "building": {"type": ["string", "null"]},
                "unit": {"type": ["string", "null"]},
                "property_type": {"type": ["string", "null"]},
                "size": {
                    "type": ["string", "null"],
                    "description": "Unit size as printed, e.g. 'Studio', '1 B/R', '2 B/R'.",
                },
                "contract_start": {
                    "type": ["string", "null"],
                    "description": "Start of the CURRENT term, DD/MM/YYYY.",
                },
                "contract_expiry": {
                    "type": ["string", "null"],
                    "description": "End of the CURRENT term, DD/MM/YYYY.",
                },
                "original_occupancy_start": {
                    "type": ["string", "null"],
                    "description": (
                        "Date the tenant FIRST occupied these premises, if stated. "
                        "This is what Article 9's two-year rule turns on, and it is "
                        "often earlier than the current term. Null if not stated."
                    ),
                },
                "notice_served": {
                    "type": ["string", "null"],
                    "description": "Date any notice of amendment or increase was served, DD/MM/YYYY.",
                },
                "security_deposit": {"type": ["string", "null"]},
                "payment_terms": {"type": ["string", "null"]},
                "document_notes": {
                    "type": "string",
                    "description": (
                        "Anything about legibility or document type the tenant should "
                        "know: scanned quality, missing pages, fields you could not read."
                    ),
                },
            },
            "required": ["annual_rent", "area", "size", "document_notes"],
        },
    },
    {
        "name": "lookup_benchmark",
        "description": (
            "Look up the market rent benchmark for an area and unit size. Returns a "
            "range with a confidence level and provenance. If the area is not in the "
            "dataset this returns found=false — report that honestly and do not "
            "substitute a benchmark for a different area."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "area": {"type": "string", "description": "Area name as read from the contract."},
                "size": {
                    "type": "string",
                    "enum": ["studio", "1br", "2br", "3br"],
                    "description": "Normalised unit size.",
                },
            },
            "required": ["area", "size"],
        },
    },
    {
        "name": "calculate_legal_max",
        "description": (
            "Apply Decree 43/2013 and the related statutory checks. This performs ALL "
            "the arithmetic — do not compute percentages or ceilings yourself, and do "
            "not restate figures this tool did not return. It applies the Article 1 "
            "tier table, the Article 9 two-year freeze, and the Article 14 notice "
            "requirement, and returns the resulting position with citations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "current_annual_rent": {"type": "number"},
                "area": {"type": "string"},
                "size": {"type": "string", "enum": ["studio", "1br", "2br", "3br"]},
                "original_occupancy_start": {
                    "type": ["string", "null"],
                    "description": "DD/MM/YYYY. Null if the contract does not state it.",
                },
                "notice_served": {"type": ["string", "null"], "description": "DD/MM/YYYY or null."},
                "contract_expiry": {"type": ["string", "null"], "description": "DD/MM/YYYY or null."},
                "proposed_annual_rent": {
                    "type": ["number", "null"],
                    "description": "What the landlord is asking, if known, so it can be compared.",
                },
            },
            "required": ["current_annual_rent", "area", "size"],
        },
    },
    {
        "name": "check_clauses",
        "description": (
            "Check contract clauses against Dubai tenancy law. For each clause, quote "
            "it from the contract and cite the provision id it conflicts with. Valid "
            "ids come from the corpus supplied in your instructions — an id that does "
            "not exist is rejected, so cite only ids you were given. The handler "
            "returns the verbatim statutory text for each accepted citation. Do not "
            "flag a clause merely because it is unfavourable: some one-sided-looking "
            "terms are the statutory default."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "clause_text": {
                                "type": "string",
                                "description": "The clause as written in the contract, quoted.",
                            },
                            "provision_id": {
                                "type": "string",
                                "description": "Corpus id of the provision it conflicts with.",
                            },
                            "concern": {
                                "type": "string",
                                "description": "One or two sentences on why they conflict.",
                            },
                            "severity": {
                                "type": "string",
                                "enum": ["conflicts", "questionable", "lawful"],
                                "description": (
                                    "'lawful' is for clauses you checked and cleared — "
                                    "record those too so the tenant sees what was reviewed."
                                ),
                            },
                        },
                        "required": ["clause_text", "provision_id", "concern", "severity"],
                    },
                }
            },
            "required": ["findings"],
        },
    },
    {
        "name": "generate_talking_points",
        "description": (
            "Produce the plain-language points the tenant can actually use, in the "
            "order they should raise them. Every point that makes a legal claim must "
            "carry a provision id already established earlier in this audit; ids are "
            "verified and unknown ones are rejected. Write for someone with no legal "
            "training who is about to have an awkward conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict_summary": {
                    "type": "string",
                    "description": "Two sentences maximum. The number, the legal maximum, the gap.",
                },
                "points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "point": {"type": "string", "description": "What to say, in plain words."},
                            "provision_id": {
                                "type": ["string", "null"],
                                "description": "Corpus id backing this point, or null if it makes no legal claim.",
                            },
                        },
                        "required": ["point", "provision_id"],
                    },
                },
                "cannot_determine": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Anything you could not establish, and why. Be explicit — an "
                        "honest gap is more useful to the tenant than a guess."
                    ),
                },
            },
            "required": ["verdict_summary", "points", "cannot_determine"],
        },
    },
]


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------


@dataclass
class ToolResult:
    """What a handler returns: payload for the model, plus render metadata."""

    payload: dict
    display: dict
    is_error: bool = False


def _handle_parse_contract(args: dict) -> ToolResult:
    rent = parse_money(args.get("annual_rent"))
    proposed = parse_money(args.get("proposed_rent"))
    size = normalise_size(args.get("size"))
    area_raw = args.get("area")
    area_canonical = legal.resolve_area(area_raw) if area_raw else None

    dates = {
        key: parse_date(args.get(key))
        for key in ("contract_start", "contract_expiry", "original_occupancy_start", "notice_served")
    }

    unresolved: list[str] = []
    if rent is None:
        unresolved.append("annual rent could not be read as a number")
    if size is None:
        unresolved.append(f"unit size {args.get('size')!r} could not be normalised")
    if area_raw and area_canonical is None:
        unresolved.append(
            f"area {area_raw!r} is not in the benchmark dataset "
            f"(known areas: {', '.join(legal.known_areas())})"
        )
    for key, value in dates.items():
        if args.get(key) and value is None:
            unresolved.append(f"{key} {args.get(key)!r} is not a recognisable date")

    payload = {
        "annual_rent": rent,
        "proposed_rent": proposed,
        "size_normalised": size,
        "area_as_written": area_raw,
        "area_canonical": area_canonical,
        "dates": {k: (v.isoformat() if v else None) for k, v in dates.items()},
        "unresolved": unresolved,
        "note": (
            "Fields listed in 'unresolved' must be reported to the tenant as "
            "undetermined. Do not substitute a value for them."
        ),
    }
    return ToolResult(
        payload=payload,
        display={
            "Annual rent": f"AED {rent:,.0f}" if rent else "could not read",
            "Proposed rent": f"AED {proposed:,.0f}" if proposed else "not stated",
            "Property": f"{size or '?'} in {area_canonical or area_raw or '?'}",
            "Original occupancy": payload["dates"]["original_occupancy_start"] or "not stated",
            "Notice served": payload["dates"]["notice_served"] or "not stated",
            "Unresolved fields": unresolved or "none",
        },
    )


def _handle_lookup_benchmark(args: dict) -> ToolResult:
    area, size = args.get("area", ""), args.get("size", "")
    bench = legal.lookup_benchmark(area, size)
    if bench is None:
        resolved = legal.resolve_area(area)
        reason = (
            f"'{area}' is not in the benchmark dataset."
            if resolved is None
            else f"No benchmark is held for a {size} in {resolved}."
        )
        return ToolResult(
            payload={
                "found": False,
                "reason": reason,
                "known_areas": legal.known_areas(),
                "note": "Report this gap honestly. Do not use a different area's benchmark.",
            },
            display={"Result": f"No benchmark — {reason}"},
        )

    return ToolResult(
        payload={
            "found": True,
            "area": bench.area,
            "size": bench.size,
            "annual_rent_low": bench.low,
            "annual_rent_high": bench.high,
            "confidence": bench.confidence,
            "source_kind": bench.source_kind,
            "snapshot_date": bench.snapshot_date,
            "provenance_label": bench.label,
            "sample_contracts": bench.samples,
        },
        display={
            "Benchmark": f"AED {bench.low:,} – {bench.high:,} per year",
            "For": f"{bench.size} in {bench.area}",
            "Confidence": bench.confidence,
            "Source": bench.label,
        },
    )


def _handle_calculate_legal_max(args: dict) -> ToolResult:
    rent = parse_money(args.get("current_annual_rent"))
    if rent is None:
        return ToolResult(
            payload={"determinable": False, "reason": "current_annual_rent was not a positive number"},
            display={"Result": "Cannot calculate — no readable rent"},
            is_error=True,
        )

    verdict = legal.assess(
        current_rent=rent,
        area=args.get("area", ""),
        size=args.get("size", ""),
        tenancy_start=parse_date(args.get("original_occupancy_start")),
    )

    notice = legal.notice_compliance(
        parse_date(args.get("notice_served")),
        parse_date(args.get("contract_expiry")),
    )

    if not verdict.determinable:
        return ToolResult(
            payload={
                "determinable": False,
                "reason": verdict.reason_if_not,
                "notice_check": {
                    "determinable": notice.determinable,
                    "days_given": notice.days_given,
                    "compliant": notice.compliant,
                    "reason": notice.reason,
                    "citation": notice.citation,
                },
            },
            display={"Result": verdict.reason_if_not or "Cannot determine"},
        )

    proposed = parse_money(args.get("proposed_annual_rent"))
    ceiling = verdict.max_lawful_rent()

    payload: dict[str, Any] = {
        "determinable": True,
        "current_annual_rent": rent,
        "proposed_annual_rent": proposed,
        "proposed_increase_pct": (
            round((proposed - rent) / rent * 100, 1) if proposed else None
        ),
        "benchmark_low": verdict.benchmark.low,
        "benchmark_high": verdict.benchmark.high,
        "benchmark_confidence": verdict.benchmark.confidence,
        "gap_below_benchmark_pct": [
            round(verdict.pct_below_low, 1),
            round(verdict.pct_below_high, 1),
        ],
        "max_increase_pct": [verdict.max_increase_low, verdict.max_increase_high],
        "max_increase_is_single_figure": verdict.is_single_figure,
        "permitted_increase_pct": verdict.permitted_increase_pct,
        "max_lawful_annual_rent": [round(ceiling[0]), round(ceiling[1])] if ceiling else None,
        # Precomputed so the model never has to subtract. A live run derived this
        # figure itself and got it right, but the rule is that no number in a
        # verdict comes from model arithmetic — so the tool supplies it.
        "excess_over_lawful_aed": (
            round(proposed - ceiling[1])
            if proposed and ceiling and proposed > ceiling[1]
            else None
        ),
        "article_9_blocks_increase": verdict.article_9_blocks_increase,
        "two_year_freeze_until": (
            verdict.two_year_date.isoformat() if verdict.two_year_date else None
        ),
        "notice_check": {
            "determinable": notice.determinable,
            "days_given": notice.days_given,
            "compliant": notice.compliant,
            "reason": notice.reason,
            "citation": notice.citation,
        },
        "citations": verdict.citations,
        "notes": verdict.notes,
        "band_edge_interpretation": (
            "Gaps are floored to a whole percent before banding. Article 1 states "
            "its bands in whole percentages, so fractional gaps are textually "
            "unaddressed; flooring yields the lower permitted increase. This is an "
            "interpretation, not a provision — say so if it affects the outcome."
        ),
    }

    if verdict.article_9_blocks_increase:
        headline = "No increase permitted — Article 9 two-year freeze"
    elif verdict.is_single_figure:
        headline = f"Maximum lawful increase: {verdict.max_increase_low}%"
    else:
        headline = (
            f"Maximum lawful increase: between {verdict.max_increase_low}% and "
            f"{verdict.max_increase_high}%"
        )

    display = {
        "Verdict": headline,
        "Their rent now": f"AED {rent:,.0f}",
        "Landlord asking": f"AED {proposed:,.0f} (+{payload['proposed_increase_pct']}%)" if proposed else "not stated",
        "Benchmark": f"AED {verdict.benchmark.low:,} – {verdict.benchmark.high:,}",
        "Lawful ceiling": f"AED {ceiling[0]:,.0f} – {ceiling[1]:,.0f}" if ceiling else "n/a",
        "Notice (90 days)": notice.reason if notice.determinable else "cannot check",
    }
    if payload["excess_over_lawful_aed"]:
        display["Excess demanded"] = f"AED {payload['excess_over_lawful_aed']:,} above the lawful ceiling"
    return ToolResult(payload=payload, display=display)


def _handle_check_clauses(args: dict) -> ToolResult:
    findings = args.get("findings") or []
    accepted, rejected = [], []

    for item in findings:
        pid = item.get("provision_id", "")
        prov = legal.provision(pid)
        if prov is None:
            rejected.append(
                {
                    "provision_id": pid,
                    "error": (
                        f"'{pid}' is not a provision in the corpus. You may not cite "
                        "it. Re-cite using an id from your instructions, or drop the "
                        "finding."
                    ),
                }
            )
            continue

        verbatim = prov.get("quote")
        accepted.append(
            {
                "clause_text": item.get("clause_text"),
                "concern": item.get("concern"),
                "severity": item.get("severity"),
                "provision_id": pid,
                "instrument": prov["instrument"],
                "article": prov["article"],
                "short_title": prov["short_title"],
                "statutory_text": verbatim or prov.get("summary"),
                "is_verbatim_quote": verbatim is not None,
                "quote_caveat": prov.get("quote_note"),
            }
        )

    payload = {
        "accepted": accepted,
        "rejected": rejected,
        "note": (
            "Where is_verbatim_quote is false the text is a summary, not a "
            "quotation — do not present it inside quotation marks."
        ),
    }
    display = {
        "Clauses checked": len(findings),
        "Conflicts found": sum(1 for a in accepted if a["severity"] == "conflicts"),
        "Questionable": sum(1 for a in accepted if a["severity"] == "questionable"),
        "Reviewed and lawful": sum(1 for a in accepted if a["severity"] == "lawful"),
        "Citations rejected": len(rejected),
    }
    return ToolResult(payload=payload, display=display, is_error=bool(rejected))


def _handle_generate_talking_points(args: dict) -> ToolResult:
    points = args.get("points") or []
    verified, rejected = [], []

    for item in points:
        pid = item.get("provision_id")
        if pid in (None, "", "null"):
            verified.append({"point": item.get("point"), "provision_id": None})
            continue
        prov = legal.provision(pid)
        if prov is None:
            rejected.append({"provision_id": pid, "point": item.get("point")})
            continue
        verified.append(
            {
                "point": item.get("point"),
                "provision_id": pid,
                "citation": f"{prov['instrument']}, Article {prov['article']}",
            }
        )

    payload = {
        "verdict_summary": args.get("verdict_summary"),
        "points": verified,
        "rejected_citations": rejected,
        "cannot_determine": args.get("cannot_determine") or [],
    }
    if rejected:
        payload["note"] = (
            "Some points cited provision ids that do not exist and were dropped. "
            "Re-issue them with a valid id or without a legal claim."
        )
    display = {
        "Summary": args.get("verdict_summary"),
        "Points": len(verified),
        "Open questions": len(payload["cannot_determine"]),
        "Citations rejected": len(rejected),
    }
    return ToolResult(payload=payload, display=display, is_error=bool(rejected))


HANDLERS = {
    "parse_contract": _handle_parse_contract,
    "lookup_benchmark": _handle_lookup_benchmark,
    "calculate_legal_max": _handle_calculate_legal_max,
    "check_clauses": _handle_check_clauses,
    "generate_talking_points": _handle_generate_talking_points,
}


def execute(name: str, args: dict) -> ToolResult:
    handler = HANDLERS.get(name)
    if handler is None:
        return ToolResult(
            payload={"error": f"Unknown tool '{name}'."},
            display={"Error": f"Unknown tool '{name}'"},
            is_error=True,
        )
    try:
        return handler(args)
    except Exception as exc:  # noqa: BLE001 - surface to the model, never crash the run
        return ToolResult(
            payload={"error": f"{type(exc).__name__}: {exc}"},
            display={"Error": f"{type(exc).__name__}: {exc}"},
            is_error=True,
        )
