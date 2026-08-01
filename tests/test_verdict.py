"""Tests for verdict classification.

The property under test throughout: a tier-based conclusion drawn from an
indicative benchmark must never be stated as settled law, while a conclusion
from contract dates alone may be.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import verdict  # noqa: E402
from src.verdict import Outcome  # noqa: E402

INDICATIVE = {"found": True, "source_kind": "indicative_market_reports",
              "confidence": "low", "snapshot_date": "2026-07-29"}
OFFICIAL = {"found": True, "source_kind": "dld_registered_contracts",
            "confidence": "high", "snapshot_date": "2026-07-30"}

BASE = {
    "determinable": True,
    "proposed_increase_pct": 15.0,
    "max_increase_pct": [0, 0],
    "max_increase_is_single_figure": True,
    "excess_over_lawful_aed": 17550,
    "article_9_blocks_increase": False,
    "notice_check": {"determinable": True, "compliant": True, "days_given": 108},
}


class TestNeverOverclaims(unittest.TestCase):
    def test_excess_on_indicative_data_is_not_called_unlawful(self):
        v = verdict.classify(BASE, INDICATIVE)
        self.assertEqual(v.outcome, Outcome.POSSIBLY_ABOVE)
        text = (v.headline + v.explanation).lower()
        self.assertIn("appears to exceed", text)
        for forbidden in ("is unlawful", "is illegal", "violates the law"):
            self.assertNotIn(forbidden, text)

    def test_indicative_result_tells_the_user_to_verify(self):
        v = verdict.classify(BASE, INDICATIVE)
        self.assertIn("official", v.explanation.lower())
        self.assertFalse(v.benchmark_is_official)

    def test_official_data_drops_the_verification_caveat(self):
        v = verdict.classify(BASE, OFFICIAL)
        self.assertTrue(v.benchmark_is_official)
        self.assertNotIn("indicative", v.explanation.lower())

    def test_indicative_excess_is_warning_not_risk_tone(self):
        """Colour must not imply more certainty than the data supports."""
        self.assertEqual(verdict.classify(BASE, INDICATIVE).tone, "warning")
        self.assertEqual(verdict.classify(BASE, OFFICIAL).tone, "risk")


class TestBenchmarkIndependentFindings(unittest.TestCase):
    """Article 9 and Article 14 come from contract dates, not market data."""

    def test_article_9_is_stated_plainly_even_on_indicative_data(self):
        calculation = dict(BASE, article_9_blocks_increase=True,
                           two_year_freeze_until="2027-06-01")
        v = verdict.classify(calculation, INDICATIVE)
        self.assertEqual(v.tone, "risk")
        self.assertIn("does not depend on market data", v.explanation)

    def test_article_9_names_the_freeze_date(self):
        calculation = dict(BASE, article_9_blocks_increase=True,
                           two_year_freeze_until="2027-06-01")
        self.assertIn("2027-06-01", verdict.classify(calculation, INDICATIVE).explanation)

    def test_short_notice_is_listed_as_a_definitive_finding(self):
        calculation = dict(
            BASE, notice_check={"determinable": True, "compliant": False, "days_given": 76}
        )
        findings = verdict.classify(calculation, INDICATIVE).definitive_findings
        self.assertTrue(any("76 days" in f for f in findings))

    def test_compliant_notice_produces_no_finding(self):
        self.assertEqual(verdict.classify(BASE, INDICATIVE).definitive_findings, [])

    def test_unverifiable_notice_produces_no_finding(self):
        calculation = dict(BASE, notice_check={"determinable": False})
        self.assertEqual(verdict.classify(calculation, INDICATIVE).definitive_findings, [])


class TestOtherOutcomes(unittest.TestCase):
    def test_within_range_when_nothing_is_owed(self):
        calculation = dict(BASE, proposed_increase_pct=0.0, excess_over_lawful_aed=None)
        self.assertEqual(verdict.classify(calculation, INDICATIVE).outcome,
                         Outcome.WITHIN_RANGE)

    def test_missing_proposed_rent_does_not_invent_a_dispute(self):
        calculation = dict(BASE, proposed_increase_pct=None, excess_over_lawful_aed=None)
        v = verdict.classify(calculation, INDICATIVE)
        self.assertEqual(v.outcome, Outcome.VERIFICATION_REQUIRED)
        self.assertIn("nothing to compare", v.explanation)

    def test_undeterminable_calculation_surfaces_the_reason(self):
        v = verdict.classify(
            {"determinable": False, "reason": "'Narnia' is not in the dataset."},
            {"found": False},
        )
        self.assertEqual(v.outcome, Outcome.UNDETERMINED)
        self.assertIn("Narnia", v.explanation)

    def test_empty_calculation_does_not_crash(self):
        v = verdict.classify({}, {})
        self.assertEqual(v.outcome, Outcome.UNDETERMINED)

    def test_every_outcome_has_a_label_and_tone(self):
        for outcome in Outcome:
            self.assertIn(outcome, verdict.STATUS_LABELS)
            self.assertIn(outcome, verdict.TONES)

    def test_range_is_rendered_when_tiers_differ(self):
        calculation = dict(BASE, max_increase_pct=[0, 10],
                           max_increase_is_single_figure=False)
        self.assertIn("0%–10%", verdict.classify(calculation, INDICATIVE).explanation)


if __name__ == "__main__":
    unittest.main()
