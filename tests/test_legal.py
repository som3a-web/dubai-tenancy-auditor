"""Tests for the legal engine.

Run: python -m unittest discover -s tests -v

Stdlib unittest deliberately — no test dependency to install at hour 40.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import legal  # noqa: E402


def _nearest_rounding_band(pct_below: float) -> int:
    """Reference implementation of the round-to-nearest reading we rejected.

    Kept so the property test below can assert that flooring never permits a
    larger increase than nearest would have.
    """
    p = round(pct_below)
    if p <= 10:
        return 0
    if p <= 20:
        return 5
    if p <= 30:
        return 10
    if p <= 40:
        return 15
    return 20


class TestTierTable(unittest.TestCase):
    """Decree 43/2013 Article 1. These bands are the product."""

    def test_every_band_boundary(self):
        cases = [
            (-25.0, 0),   # rent well above benchmark
            (-0.1, 0),
            (0.0, 0),
            (5.0, 0),
            (10.0, 0),    # "up to ten percent" -> no increase
            (11.0, 5),
            (15.0, 5),
            (20.0, 5),
            (21.0, 10),
            (30.0, 10),
            (31.0, 15),
            (40.0, 15),
            (41.0, 20),
            (75.0, 20),
        ]
        for gap, expected in cases:
            with self.subTest(gap=gap):
                self.assertEqual(legal.max_increase_for_gap(gap)[0], expected)

    def test_fractional_gaps_floor_to_whole_percent(self):
        """Fractional gaps floor, never round to nearest.

        Article 1's bands are whole percentages, so 10.5% is in a textual gap.
        Flooring gives the tenant-protective reading and puts every band edge
        on the integer the decree names. See max_increase_for_gap's docstring.
        """
        cases = [
            (10.4, 0),
            (10.5, 0),   # would be 5% under round-to-nearest
            (10.9, 0),   # still inside "up to ten percent"
            (11.0, 5),   # first point the 5% band is clearly reached
            (20.4, 5),
            (20.9, 5),   # would be 10% under round-to-nearest
            (21.0, 10),
            (40.9, 15),
            (41.0, 20),
        ]
        for gap, expected in cases:
            with self.subTest(gap=gap):
                self.assertEqual(legal.max_increase_for_gap(gap)[0], expected)

    def test_flooring_never_favours_the_landlord_over_nearest(self):
        """Flooring must never permit a HIGHER increase than round-to-nearest."""
        for tenth in range(-200, 1000):
            gap = tenth / 10
            floored = legal.max_increase_for_gap(gap)[0]
            nearest_band = _nearest_rounding_band(gap)
            with self.subTest(gap=gap):
                self.assertLessEqual(floored, nearest_band)


    def test_tier_quote_comes_from_the_verified_corpus(self):
        _, quote = legal.max_increase_for_gap(25.0)
        self.assertIn("ten percent (10%)", quote)
        self.assertIn("twenty-one percent (21%)", quote)


class TestPercentBelow(unittest.TestCase):
    def test_basic_gap(self):
        self.assertAlmostEqual(legal.percent_below(88_000, 100_000), 12.0)

    def test_rent_above_benchmark_is_negative(self):
        self.assertAlmostEqual(legal.percent_below(110_000, 100_000), -10.0)

    def test_equal_is_zero(self):
        self.assertAlmostEqual(legal.percent_below(100_000, 100_000), 0.0)

    def test_zero_benchmark_raises(self):
        with self.assertRaises(ValueError):
            legal.percent_below(50_000, 0)


class TestAreaResolution(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(legal.resolve_area("Dubai Marina"), "Dubai Marina")

    def test_alias(self):
        self.assertEqual(legal.resolve_area("JLT"), "Jumeirah Lake Towers")
        self.assertEqual(legal.resolve_area("JVC"), "Jumeirah Village Circle")

    def test_case_insensitive(self):
        self.assertEqual(legal.resolve_area("dubai marina"), "Dubai Marina")
        self.assertEqual(legal.resolve_area("jlt"), "Jumeirah Lake Towers")

    def test_no_fuzzy_matching(self):
        # Resolving this to "Al Barsha" would give a confident benchmark for
        # the wrong neighbourhood. It must fail instead.
        self.assertIsNone(legal.resolve_area("Al Barsha South"))
        self.assertIsNone(legal.resolve_area("Marina Heights Tower 2"))

    def test_empty_and_unknown(self):
        self.assertIsNone(legal.resolve_area(""))
        self.assertIsNone(legal.resolve_area("Nowhereville"))


class TestBenchmarkLookup(unittest.TestCase):
    def test_known_cell(self):
        bench = legal.lookup_benchmark("Dubai Marina", "1br")
        self.assertIsNotNone(bench)
        self.assertEqual(bench.area, "Dubai Marina")
        self.assertLess(bench.low, bench.high)
        self.assertIn(bench.confidence, {"high", "low"})

    def test_unknown_area_returns_none(self):
        self.assertIsNone(legal.lookup_benchmark("Atlantis", "1br"))

    def test_invalid_size_returns_none(self):
        self.assertIsNone(legal.lookup_benchmark("Dubai Marina", "penthouse"))

    def test_missing_cell_returns_none(self):
        # Discovery Gardens has no 3br entry in the dataset.
        self.assertIsNone(legal.lookup_benchmark("Discovery Gardens", "3br"))

    def test_alias_lookup_works(self):
        self.assertIsNotNone(legal.lookup_benchmark("JLT", "2br"))


class TestTwoYearAnniversary(unittest.TestCase):
    def test_ordinary_date(self):
        self.assertEqual(
            legal.two_year_anniversary(date(2025, 3, 15)), date(2027, 3, 15)
        )

    def test_leap_day_falls_back_to_28_feb(self):
        self.assertEqual(
            legal.two_year_anniversary(date(2024, 2, 29)), date(2026, 2, 28)
        )


class TestAssess(unittest.TestCase):
    def test_unreadable_rent_is_not_determinable(self):
        v = legal.assess(0, "Dubai Marina", "1br")
        self.assertFalse(v.determinable)
        self.assertIn("could not be read", v.reason_if_not)

    def test_unknown_area_is_not_determinable_and_says_why(self):
        v = legal.assess(90_000, "Narnia", "1br")
        self.assertFalse(v.determinable)
        self.assertIn("Narnia", v.reason_if_not)
        self.assertIn("cannot be determined", v.reason_if_not)

    def test_missing_size_cell_is_not_determinable(self):
        v = legal.assess(90_000, "Discovery Gardens", "3br")
        self.assertFalse(v.determinable)
        self.assertIn("Discovery Gardens", v.reason_if_not)

    def test_determinable_case_populates_range(self):
        v = legal.assess(100_000, "Dubai Marina", "1br")
        self.assertTrue(v.determinable)
        self.assertIsNotNone(v.pct_below_low)
        self.assertLessEqual(v.pct_below_low, v.pct_below_high)
        self.assertLessEqual(v.max_increase_low, v.max_increase_high)

    def test_article_9_blocks_increase_within_two_years(self):
        # Tenancy started 14 months before assessment.
        v = legal.assess(
            40_000,
            "Deira",
            "1br",
            tenancy_start=date(2025, 6, 1),
            assessment_date=date(2026, 8, 1),
        )
        self.assertTrue(v.determinable)
        self.assertTrue(v.article_9_blocks_increase)
        self.assertEqual(v.permitted_increase_pct, 0)
        self.assertIn("law-26-2007-art-9", v.citations)
        self.assertEqual(v.two_year_date, date(2027, 6, 1))

    def test_article_9_does_not_block_after_two_years(self):
        v = legal.assess(
            40_000,
            "Deira",
            "1br",
            tenancy_start=date(2023, 1, 1),
            assessment_date=date(2026, 8, 1),
        )
        self.assertFalse(v.article_9_blocks_increase)

    def test_article_9_boundary_is_exclusive_on_the_day(self):
        # On the anniversary itself the freeze has elapsed.
        v = legal.assess(
            40_000,
            "Deira",
            "1br",
            tenancy_start=date(2024, 8, 1),
            assessment_date=date(2026, 8, 1),
        )
        self.assertFalse(v.article_9_blocks_increase)

    def test_article_9_blocked_rent_ceiling_is_unchanged_rent(self):
        v = legal.assess(
            40_000,
            "Deira",
            "1br",
            tenancy_start=date(2025, 6, 1),
            assessment_date=date(2026, 8, 1),
        )
        self.assertEqual(v.max_lawful_rent(), (40_000, 40_000))

    def test_rent_above_benchmark_permits_nothing(self):
        # Well above the top of the Deira 1br range.
        v = legal.assess(200_000, "Deira", "1br", assessment_date=date(2026, 8, 1))
        self.assertTrue(v.determinable)
        self.assertEqual(v.max_increase_low, 0)
        self.assertEqual(v.max_increase_high, 0)
        self.assertEqual(v.permitted_increase_pct, 0)

    def test_low_confidence_benchmark_is_flagged_in_notes(self):
        v = legal.assess(100_000, "Dubai Marina", "1br")
        if v.benchmark.confidence != "high":
            self.assertTrue(
                any("indicative" in note for note in v.notes),
                "low-confidence benchmark must be disclosed in notes",
            )

    def test_no_tenancy_start_means_article_9_untested(self):
        v = legal.assess(100_000, "Dubai Marina", "1br")
        self.assertFalse(v.article_9_blocks_increase)
        self.assertIsNone(v.two_year_date)


class TestCorpusIntegrity(unittest.TestCase):
    """The corpus is the anti-hallucination backbone; guard its shape."""

    def test_provision_lookup(self):
        self.assertIsNotNone(legal.provision("law-33-2008-art-14"))
        self.assertIsNone(legal.provision("law-99-9999-art-1"))

    def test_every_provision_is_quote_xor_summary(self):
        for item in legal.load_corpus()["provisions"]:
            with self.subTest(pid=item["id"]):
                self.assertNotEqual(
                    "quote" in item,
                    "summary" in item,
                    "a provision must carry exactly one of quote/summary",
                )

    def test_summaries_are_marked_not_verbatim(self):
        for item in legal.load_corpus()["provisions"]:
            if "summary" in item:
                with self.subTest(pid=item["id"]):
                    self.assertIn("SUMMARISED", item.get("quote_note", ""))

    def test_tier_table_is_complete_and_ordered(self):
        tiers = legal.load_corpus()["rent_increase_tiers"]["tiers"]
        self.assertEqual([t["max_increase_pct"] for t in tiers], [0, 5, 10, 15, 20])
        self.assertIsNone(tiers[-1]["max_pct_below"], "top tier must be open-ended")


if __name__ == "__main__":
    unittest.main()
