"""The legal engine: benchmark lookup and Decree 43/2013 tier calculation.

Deliberately free of any LLM involvement. The agent calls these functions as
tools; it does not do the arithmetic itself. That way the numbers in a verdict
are testable, and a wrong verdict is a failing test rather than a bad sample.

Nothing here is allowed to guess. Every function returns an explicit
"cannot determine" state rather than a plausible-looking number.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

SIZE_KEYS = ("studio", "1br", "2br", "3br")


# --------------------------------------------------------------------------
# Corpus and benchmark loading
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_corpus() -> dict:
    return json.loads((DATA_DIR / "legal_corpus.json").read_text())


@lru_cache(maxsize=1)
def load_benchmarks() -> dict:
    return json.loads((DATA_DIR / "benchmarks.json").read_text())


def provision(provision_id: str) -> dict | None:
    """Fetch one verified provision by id. Returns None if absent.

    Callers must treat None as "no such verified provision" and say so, rather
    than describing the provision from memory.
    """
    for item in load_corpus()["provisions"]:
        if item["id"] == provision_id:
            return item
    return None


# --------------------------------------------------------------------------
# Area resolution
# --------------------------------------------------------------------------


def resolve_area(raw: str) -> str | None:
    """Map a free-text area name onto a canonical benchmark area.

    Exact match, then alias, then case-insensitive match. No fuzzy matching:
    silently resolving "Al Barsha South" to "Al Barsha" would produce a
    confident benchmark for the wrong neighbourhood.
    """
    if not raw:
        return None
    data = load_benchmarks()
    areas, aliases = data["areas"], data.get("aliases", {})
    name = raw.strip()

    if name in areas:
        return name
    if name in aliases and aliases[name] in areas:
        return aliases[name]

    lowered = name.casefold()
    for candidate in areas:
        if candidate.casefold() == lowered:
            return candidate
    for alias, target in aliases.items():
        if alias.casefold() == lowered and target in areas:
            return target
    return None


def known_areas() -> list[str]:
    return sorted(load_benchmarks()["areas"])


# --------------------------------------------------------------------------
# Benchmark lookup
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Benchmark:
    area: str
    size: str
    low: int
    high: int
    confidence: str          # "high" | "low"
    source_kind: str
    snapshot_date: str
    label: str
    samples: int | None = None

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2


def lookup_benchmark(area: str, size: str) -> Benchmark | None:
    """Return the benchmark range for an area and unit size, or None.

    None means "we have no figure for this", which the caller must report as
    such. It never falls back to a city-wide average.
    """
    canonical = resolve_area(area)
    if canonical is None:
        return None
    if size not in SIZE_KEYS:
        return None

    data = load_benchmarks()
    cell = data["areas"][canonical].get(size)
    if not cell:
        return None

    prov = data["provenance"]
    samples = data.get("samples", {}).get(canonical, {}).get(size)
    return Benchmark(
        area=canonical,
        size=size,
        low=int(cell[0]),
        high=int(cell[1]),
        confidence=prov["confidence"],
        source_kind=prov["source_kind"],
        snapshot_date=prov["snapshot_date"],
        label=prov["label"],
        samples=samples,
    )


# --------------------------------------------------------------------------
# Decree 43/2013 tier calculation
# --------------------------------------------------------------------------


def percent_below(current_rent: float, benchmark: float) -> float:
    """How far current rent sits below a benchmark, as a percentage.

    Negative when the rent is at or above the benchmark.
    """
    if benchmark <= 0:
        raise ValueError("benchmark must be positive")
    return (benchmark - current_rent) / benchmark * 100.0


def max_increase_for_gap(pct_below: float) -> tuple[int, str]:
    """Apply the Article 1 tier table. Returns (max increase %, tier quote).

    Article 1 states its bands in whole percentages — "up to ten percent (10%)",
    then "eleven percent (11%) to twenty percent (20%)" — so a fractional gap
    such as 10.5% falls in a textual gap that the decree does not address.

    We resolve that by taking the FLOOR of the gap, for two reasons:

    1. Asymmetric harm. Flooring yields the lower permitted increase. If we
       report 0% and the true answer is 5%, the tenant queries it and the
       landlord produces the index — nobody loses money. If we report 5% and
       the true answer is 0%, the tenant pays rent they never owed. When the
       instrument is genuinely silent, err toward the party we advise.
    2. Consistency. Flooring puts every band edge exactly on the integer the
       decree names. Rounding to nearest would use banker's rounding, which
       sends 10.5 down to 10 but 11.5 up to 12 — indefensible in a legal
       explanation.

    This is a documented interpretation, not a provision of the decree, and the
    UI labels it as such next to any verdict sitting on a band edge.
    """
    tiers = load_corpus()["rent_increase_tiers"]["tiers"]
    rounded = math.floor(pct_below)

    if rounded <= 10:
        # Covers rent at or above the benchmark (negative gap) too.
        chosen = tiers[0]
    else:
        chosen = tiers[-1]
        for tier in tiers:
            ceiling = tier["max_pct_below"]
            if ceiling is not None and rounded <= ceiling:
                chosen = tier
                break
    return int(chosen["max_increase_pct"]), chosen["quote"]


def two_year_anniversary(start: date) -> date:
    """The date Article 9's two-year freeze expires. Handles 29 February."""
    try:
        return start.replace(year=start.year + 2)
    except ValueError:
        # 29 Feb with a non-leap target year -> 28 Feb.
        return start.replace(year=start.year + 2, day=28)


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------


@dataclass
class Verdict:
    """The outcome of applying Dubai law to one tenancy."""

    determinable: bool
    reason_if_not: str | None = None

    current_rent: float | None = None
    benchmark: Benchmark | None = None

    # Gap and permitted increase, expressed as a range because the benchmark
    # is a range. When both ends land in the same tier, low == high.
    pct_below_low: float | None = None
    pct_below_high: float | None = None
    max_increase_low: int | None = None
    max_increase_high: int | None = None

    # Article 9 overrides the tier table entirely.
    article_9_blocks_increase: bool = False
    two_year_date: date | None = None

    citations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_single_figure(self) -> bool:
        return (
            self.max_increase_low is not None
            and self.max_increase_low == self.max_increase_high
        )

    @property
    def permitted_increase_pct(self) -> int | None:
        """The permitted increase when it is unambiguous, else None."""
        if self.article_9_blocks_increase:
            return 0
        return self.max_increase_low if self.is_single_figure else None

    def max_lawful_rent(self) -> tuple[float, float] | None:
        """The lawful rent ceiling range after any permitted increase."""
        if self.current_rent is None or self.max_increase_low is None:
            return None
        if self.article_9_blocks_increase:
            return (self.current_rent, self.current_rent)
        low = self.current_rent * (1 + self.max_increase_low / 100)
        high = self.current_rent * (1 + (self.max_increase_high or 0) / 100)
        return (low, high)


def assess(
    current_rent: float,
    area: str,
    size: str,
    tenancy_start: date | None = None,
    assessment_date: date | None = None,
) -> Verdict:
    """Work out the maximum lawful increase for one tenancy.

    tenancy_start is the start of the ORIGINAL contractual relationship, not
    the current renewal — that is what Article 9 turns on.
    """
    if current_rent <= 0:
        return Verdict(
            determinable=False,
            reason_if_not="The annual rent could not be read from the contract.",
        )

    benchmark = lookup_benchmark(area, size)
    if benchmark is None:
        resolved = resolve_area(area)
        if resolved is None:
            reason = (
                f"'{area}' is not in the benchmark dataset, so the market "
                "benchmark for this property cannot be established. Without a "
                "benchmark the Decree 43 tier cannot be determined."
            )
        else:
            reason = (
                f"No benchmark figure is held for a {size} in {resolved}, so "
                "the Decree 43 tier cannot be determined."
            )
        return Verdict(determinable=False, reason_if_not=reason)

    today = assessment_date or date.today()

    # Article 9 first: it overrides the tier table outright.
    article_9_blocks = False
    anniversary = None
    if tenancy_start is not None:
        anniversary = two_year_anniversary(tenancy_start)
        article_9_blocks = today < anniversary

    # The benchmark is a range, so the gap is a range. A rent compared against
    # the LOW end of the benchmark shows the smallest gap.
    gap_at_low = percent_below(current_rent, benchmark.low)
    gap_at_high = percent_below(current_rent, benchmark.high)
    pct_low, pct_high = sorted((gap_at_low, gap_at_high))

    increase_a, quote_a = max_increase_for_gap(pct_low)
    increase_b, quote_b = max_increase_for_gap(pct_high)
    inc_low, inc_high = sorted((increase_a, increase_b))

    citations = ["decree-43-2013-art-3"]
    notes: list[str] = []

    if article_9_blocks:
        citations.insert(0, "law-26-2007-art-9")
        notes.append(
            "Article 9 of Law 26/2007 prohibits any increase before two years "
            f"have elapsed from {tenancy_start.isoformat()}. That period runs "
            f"until {anniversary.isoformat()}, so no increase is permitted on "
            "this renewal regardless of the index."
        )

    if benchmark.confidence != "high":
        notes.append(
            "The benchmark is an indicative range, not DLD registered-contract "
            "data, so the permitted increase is reported as a range. Confirm "
            "against the official Smart Rental Index before relying on it."
        )

    if inc_low != inc_high:
        notes.append(
            "The rent falls near a tier boundary: depending on where in the "
            "benchmark range the property actually sits, the permitted "
            f"increase is between {inc_low}% and {inc_high}%."
        )

    if pct_low <= 0 and pct_high <= 0:
        notes.append(
            "The rent is already at or above the benchmark, so Article 1 "
            "permits no increase."
        )

    return Verdict(
        determinable=True,
        current_rent=current_rent,
        benchmark=benchmark,
        pct_below_low=pct_low,
        pct_below_high=pct_high,
        max_increase_low=inc_low,
        max_increase_high=inc_high,
        article_9_blocks_increase=article_9_blocks,
        two_year_date=anniversary,
        citations=citations,
        notes=notes,
    )
