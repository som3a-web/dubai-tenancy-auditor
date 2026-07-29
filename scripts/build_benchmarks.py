#!/usr/bin/env python3
"""Turn a DLD registered-rental-contracts CSV into data/benchmarks.json.

The DLD open-data Rents export is behind a captcha, so the download itself is a
manual step. This script is everything after it.

    # See what the file contains and how columns map, without writing anything
    python scripts/build_benchmarks.py --dry-run data/raw/rents.csv

    # Write the real snapshot
    python scripts/build_benchmarks.py data/raw/rents.csv

Column names in DLD exports drift between years and between the Dubai Pulse and
dubailand.gov.ae variants, so columns are detected by fuzzy match and the
detection is always printed. If detection is wrong, override it explicitly:

    python scripts/build_benchmarks.py data/raw/rents.csv \
        --area-col area_name_en --rent-col annual_amount --rooms-col rooms
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "benchmarks.json"

# Candidate column names, best guess first.
CANDIDATES = {
    "area": ["area_name_en", "area_en", "area", "master_project_en", "location"],
    "rent": ["annual_amount", "contract_amount", "annual_rent", "rent_amount", "amount"],
    "rooms": ["rooms", "rooms_en", "no_of_rooms", "bedrooms", "ejari_property_type_en"],
    "usage": ["property_usage_en", "usage_en", "property_usage"],
    "start": ["contract_start_date", "start_date", "registration_date"],
}

# Minimum contracts before an area/size cell is trusted. Thin cells produce
# noisy medians, and a noisy benchmark is how you get a confidently wrong
# verdict about someone's housing.
MIN_SAMPLES = 30

# DLD exports write bedroom counts as "1 B/R", "2 B/R", "Studio" — note the
# slash. Earlier drafts of this regex missed it and silently discarded 80% of
# the file, so the separator class here is deliberately permissive.
_BEDROOM_SUFFIX = r"(?:b\s*[/.\-]?\s*r\b|bed\s*rooms?\b|bedrooms?\b|beds?\b)"

ROOM_PATTERNS = [
    ("studio", re.compile(r"\bstudio\b", re.I)),
    ("1br", re.compile(rf"\b(?:1|one)\s*{_BEDROOM_SUFFIX}", re.I)),
    ("2br", re.compile(rf"\b(?:2|two)\s*{_BEDROOM_SUFFIX}", re.I)),
    ("3br", re.compile(rf"\b(?:3|three)\s*{_BEDROOM_SUFFIX}", re.I)),
]


def normalise_rooms(raw: str) -> str | None:
    """Map a messy rooms value to studio/1br/2br/3br, or None to skip the row."""
    value = (raw or "").strip()
    if not value:
        return None
    for label, pattern in ROOM_PATTERNS:
        if pattern.search(value):
            return label
    # Bare integers appear in some exports.
    if value.isdigit():
        return {"0": "studio", "1": "1br", "2": "2br", "3": "3br"}.get(value)
    return None


def detect_column(header: list[str], kind: str, override: str | None) -> str | None:
    if override:
        if override not in header:
            sys.exit(f"error: --{kind}-col '{override}' is not in the CSV header")
        return override
    lowered = {h.lower().strip(): h for h in header}
    for candidate in CANDIDATES[kind]:
        if candidate in lowered:
            return lowered[candidate]
    # Loose contains-match as a last resort.
    for candidate in CANDIDATES[kind]:
        for low, original in lowered.items():
            if candidate in low:
                return original
    return None


def parse_rent(raw: str) -> float | None:
    try:
        value = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    # Drop obvious junk: peppercorn rents and data-entry errors.
    if value < 5_000 or value > 5_000_000:
        return None
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")
    parser.add_argument("--area-col")
    parser.add_argument("--rent-col")
    parser.add_argument("--rooms-col")
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    args = parser.parse_args()

    if not args.csv_path.exists():
        sys.exit(f"error: {args.csv_path} not found")

    with args.csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []

        area_col = detect_column(header, "area", args.area_col)
        rent_col = detect_column(header, "rent", args.rent_col)
        rooms_col = detect_column(header, "rooms", args.rooms_col)

        print(f"CSV columns detected ({len(header)} total):")
        print(f"  area  -> {area_col or 'NOT FOUND'}")
        print(f"  rent  -> {rent_col or 'NOT FOUND'}")
        print(f"  rooms -> {rooms_col or 'NOT FOUND'}")
        if not all([area_col, rent_col, rooms_col]):
            print(f"\nAvailable columns: {', '.join(header)}")
            sys.exit("\nerror: could not detect required columns; pass them explicitly")

        buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
        rows = skipped = 0
        for row in reader:
            rows += 1
            rent = parse_rent(row.get(rent_col, ""))
            rooms = normalise_rooms(row.get(rooms_col, ""))
            area = (row.get(area_col) or "").strip()
            if rent is None or rooms is None or not area:
                skipped += 1
                continue
            buckets[(area, rooms)].append(rent)

    print(f"\nRead {rows:,} rows; skipped {skipped:,} unusable.")

    # Same shape as the fallback dataset: area -> size -> [low, high].
    # Sample counts live in a parallel map so the size keys stay clean.
    areas: dict[str, dict[str, list[int]]] = defaultdict(dict)
    samples: dict[str, dict[str, int]] = defaultdict(dict)
    kept = dropped_thin = 0
    for (area, rooms), values in sorted(buckets.items()):
        if len(values) < args.min_samples:
            dropped_thin += 1
            continue
        values.sort()
        # Interquartile range, not min/max — the tails of registered-contract
        # data are full of related-party and legacy renewals.
        low = statistics.quantiles(values, n=4)[0]
        high = statistics.quantiles(values, n=4)[2]
        areas[area][rooms] = [int(round(low, -3)), int(round(high, -3))]
        samples[area][rooms] = len(values)
        kept += 1

    print(f"Kept {kept} area/size cells; dropped {dropped_thin} below {args.min_samples} samples.")
    print(f"Areas covered: {len(areas)}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    if not areas:
        sys.exit("error: no cells met the sample threshold; not overwriting benchmarks.json")

    existing_aliases = {}
    if OUTPUT_PATH.exists():
        existing_aliases = json.loads(OUTPUT_PATH.read_text()).get("aliases", {})

    payload = {
        "provenance": {
            "source_kind": "dld_registered_contracts",
            "confidence": "high",
            "snapshot_date": date.today().isoformat(),
            "label": f"Derived from {rows:,} DLD registered rental contracts, snapshot {date.today().isoformat()}",
            "description": (
                "Interquartile range of annual rents for registered Ejari contracts, "
                f"grouped by area and unit size. Cells with fewer than {args.min_samples} "
                "contracts are omitted rather than reported at low confidence. This is an "
                "area-level average and cannot reproduce RERA's building-level Smart Rental Index."
            ),
            "source_file": args.csv_path.name,
            "rows_read": rows,
            "min_samples_per_cell": args.min_samples,
        },
        "currency": "AED",
        "period": "annual",
        "areas": dict(areas),
        "samples": {area: dict(sizes) for area, sizes in samples.items()},
        "aliases": existing_aliases,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"\nWrote {OUTPUT_PATH.relative_to(REPO_ROOT)} — confidence now 'high'.")
    print("Check a few areas look sane before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
