"""Tests for the tool layer. No API calls — handlers are pure.

Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import tools  # noqa: E402


class TestParsers(unittest.TestCase):
    def test_money_formats(self):
        for raw, expected in [
            ("AED 117,000", 117_000),
            ("117000", 117_000),
            ("AED117,000.50", 117_000.50),
            ("Dhs 42,000", 42_000),
            ("  68,000  ", 68_000),
            (95_000, 95_000),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(tools.parse_money(raw), expected)

    def test_money_rejects_junk_and_nonpositive(self):
        for raw in [None, "", "not a number", "AED 0", 0, -5]:
            with self.subTest(raw=raw):
                self.assertIsNone(tools.parse_money(raw))

    def test_dates_prefer_day_first(self):
        # 01/09/2025 in a Dubai contract is 1 September, not 9 January.
        self.assertEqual(tools.parse_date("01/09/2025"), date(2025, 9, 1))
        self.assertEqual(tools.parse_date("2025-09-01"), date(2025, 9, 1))
        self.assertEqual(tools.parse_date("16 September 2025"), date(2025, 9, 16))

    def test_dates_reject_junk(self):
        for raw in [None, "", "not a date", "31/02/2025"]:
            with self.subTest(raw=raw):
                self.assertIsNone(tools.parse_date(raw))

    def test_size_normalisation(self):
        for raw, expected in [
            ("Studio", "studio"),
            ("1 B/R", "1br"),
            ("2 B/R", "2br"),
            ("3 B/R", "3br"),
            ("Two Bedroom", "2br"),
            ("Residential Studio", "studio"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(tools.normalise_size(raw), expected)

    def test_size_rejects_unknown(self):
        self.assertIsNone(tools.normalise_size("Warehouse"))
        self.assertIsNone(tools.normalise_size(None))


class TestParseContractHandler(unittest.TestCase):
    def test_clean_extraction(self):
        result = tools.execute(
            "parse_contract",
            {
                "annual_rent": "AED 117,000",
                "proposed_rent": "AED 134,550",
                "area": "Dubai Marina",
                "size": "1 B/R",
                "original_occupancy_start": "01/09/2023",
                "notice_served": "15/05/2026",
                "document_notes": "clean text PDF",
            },
        )
        self.assertEqual(result.payload["annual_rent"], 117_000)
        self.assertEqual(result.payload["area_canonical"], "Dubai Marina")
        self.assertEqual(result.payload["size_normalised"], "1br")
        self.assertEqual(result.payload["unresolved"], [])

    def test_unknown_area_is_reported_not_guessed(self):
        result = tools.execute(
            "parse_contract",
            {
                "annual_rent": "AED 90,000",
                "area": "Al Barsha South",
                "size": "1 B/R",
                "document_notes": "",
            },
        )
        self.assertIsNone(result.payload["area_canonical"])
        self.assertTrue(
            any("Al Barsha South" in u for u in result.payload["unresolved"])
        )
        # The model is told which areas exist so it can report the gap precisely.
        self.assertTrue(any("known areas" in u for u in result.payload["unresolved"]))

    def test_unreadable_rent_is_flagged(self):
        result = tools.execute(
            "parse_contract",
            {"annual_rent": None, "area": "Deira", "size": "2 B/R", "document_notes": "faint scan"},
        )
        self.assertIsNone(result.payload["annual_rent"])
        self.assertTrue(any("annual rent" in u for u in result.payload["unresolved"]))

    def test_bad_date_is_flagged_not_silently_dropped(self):
        result = tools.execute(
            "parse_contract",
            {
                "annual_rent": "AED 68,000",
                "area": "Deira",
                "size": "2 B/R",
                "notice_served": "the first of July",
                "document_notes": "",
            },
        )
        self.assertTrue(any("notice_served" in u for u in result.payload["unresolved"]))


class TestBenchmarkHandler(unittest.TestCase):
    def test_found(self):
        result = tools.execute("lookup_benchmark", {"area": "Dubai Marina", "size": "1br"})
        self.assertTrue(result.payload["found"])
        self.assertLess(result.payload["annual_rent_low"], result.payload["annual_rent_high"])
        self.assertIn(result.payload["confidence"], {"high", "low"})

    def test_not_found_lists_alternatives_and_forbids_substitution(self):
        result = tools.execute("lookup_benchmark", {"area": "Narnia", "size": "1br"})
        self.assertFalse(result.payload["found"])
        self.assertIn("known_areas", result.payload)
        self.assertIn("Do not use a different area", result.payload["note"])


class TestCalculateLegalMaxHandler(unittest.TestCase):
    def test_headline_case_is_zero_percent(self):
        result = tools.execute(
            "calculate_legal_max",
            {
                "current_annual_rent": 117_000,
                "area": "Dubai Marina",
                "size": "1br",
                "original_occupancy_start": "01/09/2023",
                "notice_served": "15/05/2026",
                "contract_expiry": "31/08/2026",
                "proposed_annual_rent": 134_550,
            },
        )
        self.assertTrue(result.payload["determinable"])
        self.assertEqual(result.payload["permitted_increase_pct"], 0)
        self.assertEqual(result.payload["proposed_increase_pct"], 15.0)
        self.assertTrue(result.payload["notice_check"]["compliant"])

    def test_article_9_case(self):
        result = tools.execute(
            "calculate_legal_max",
            {
                "current_annual_rent": 42_000,
                "area": "Jumeirah Village Circle",
                "size": "studio",
                "original_occupancy_start": "01/06/2025",
            },
        )
        self.assertTrue(result.payload["article_9_blocks_increase"])
        self.assertEqual(result.payload["permitted_increase_pct"], 0)

    def test_short_notice_is_detected(self):
        result = tools.execute(
            "calculate_legal_max",
            {
                "current_annual_rent": 68_000,
                "area": "Deira",
                "size": "2br",
                "notice_served": "01/07/2026",
                "contract_expiry": "15/09/2026",
            },
        )
        self.assertFalse(result.payload["notice_check"]["compliant"])
        self.assertEqual(result.payload["notice_check"]["days_given"], 76)

    def test_unknown_area_is_not_determinable(self):
        result = tools.execute(
            "calculate_legal_max",
            {"current_annual_rent": 90_000, "area": "Narnia", "size": "1br"},
        )
        self.assertFalse(result.payload["determinable"])

    def test_bad_rent_is_an_error_not_a_number(self):
        result = tools.execute(
            "calculate_legal_max",
            {"current_annual_rent": 0, "area": "Deira", "size": "2br"},
        )
        self.assertTrue(result.is_error)
        self.assertFalse(result.payload["determinable"])

    def test_band_edge_interpretation_is_disclosed_to_the_model(self):
        result = tools.execute(
            "calculate_legal_max",
            {"current_annual_rent": 68_000, "area": "Deira", "size": "2br"},
        )
        self.assertIn("interpretation", result.payload["band_edge_interpretation"])


class TestCheckClausesHandler(unittest.TestCase):
    """This is the anti-hallucination guarantee. It must hold."""

    def test_valid_citation_returns_verbatim_statute(self):
        result = tools.execute(
            "check_clauses",
            {
                "findings": [
                    {
                        "clause_text": "deposit is non-refundable",
                        "provision_id": "law-26-2007-art-20",
                        "concern": "Article 20 contemplates refund.",
                        "severity": "conflicts",
                    }
                ]
            },
        )
        accepted = result.payload["accepted"][0]
        self.assertTrue(accepted["is_verbatim_quote"])
        self.assertIn("refund such deposit", accepted["statutory_text"])
        self.assertEqual(result.payload["rejected"], [])

    def test_invented_provision_id_is_rejected(self):
        result = tools.execute(
            "check_clauses",
            {
                "findings": [
                    {
                        "clause_text": "anything",
                        "provision_id": "law-99-2099-art-42",
                        "concern": "made up",
                        "severity": "conflicts",
                    }
                ]
            },
        )
        self.assertEqual(result.payload["accepted"], [])
        self.assertEqual(len(result.payload["rejected"]), 1)
        self.assertTrue(result.is_error, "a rejected citation must surface as an error")
        self.assertIn("may not cite it", result.payload["rejected"][0]["error"])

    def test_summary_provision_is_marked_not_quotable(self):
        result = tools.execute(
            "check_clauses",
            {
                "findings": [
                    {
                        "clause_text": "eviction on 30 days notice",
                        "provision_id": "law-33-2008-art-25-grounds",
                        "concern": "grounds are a closed list",
                        "severity": "conflicts",
                    }
                ]
            },
        )
        accepted = result.payload["accepted"][0]
        self.assertFalse(accepted["is_verbatim_quote"])
        self.assertIn("SUMMARISED", accepted["quote_caveat"])
        self.assertIn("do not present it inside quotation marks", result.payload["note"])

    def test_mixed_valid_and_invalid_keeps_the_valid_one(self):
        result = tools.execute(
            "check_clauses",
            {
                "findings": [
                    {
                        "clause_text": "a",
                        "provision_id": "law-26-2007-art-7",
                        "concern": "x",
                        "severity": "conflicts",
                    },
                    {
                        "clause_text": "b",
                        "provision_id": "not-a-real-id",
                        "concern": "y",
                        "severity": "conflicts",
                    },
                ]
            },
        )
        self.assertEqual(len(result.payload["accepted"]), 1)
        self.assertEqual(len(result.payload["rejected"]), 1)

    def test_lawful_severity_is_counted_separately(self):
        result = tools.execute(
            "check_clauses",
            {
                "findings": [
                    {
                        "clause_text": "tenant pays government fees",
                        "provision_id": "law-26-2007-art-22",
                        "concern": "This is the statutory default.",
                        "severity": "lawful",
                    }
                ]
            },
        )
        self.assertEqual(result.display["Reviewed and lawful"], 1)
        self.assertEqual(result.display["Conflicts found"], 0)


class TestTalkingPointsHandler(unittest.TestCase):
    def test_valid_citation_is_expanded(self):
        result = tools.execute(
            "generate_talking_points",
            {
                "verdict_summary": "No increase is lawful.",
                "points": [{"point": "Cite the two-year rule.", "provision_id": "law-26-2007-art-9"}],
                "cannot_determine": [],
            },
        )
        self.assertIn("Article 9", result.payload["points"][0]["citation"])
        self.assertEqual(result.payload["rejected_citations"], [])

    def test_point_without_a_legal_claim_is_allowed(self):
        result = tools.execute(
            "generate_talking_points",
            {
                "verdict_summary": "s",
                "points": [{"point": "Stay calm and put it in writing.", "provision_id": None}],
                "cannot_determine": [],
            },
        )
        self.assertEqual(len(result.payload["points"]), 1)
        self.assertIsNone(result.payload["points"][0]["provision_id"])

    def test_invented_citation_is_dropped_and_flagged(self):
        result = tools.execute(
            "generate_talking_points",
            {
                "verdict_summary": "s",
                "points": [{"point": "Claim something invented.", "provision_id": "fake-id"}],
                "cannot_determine": [],
            },
        )
        self.assertEqual(result.payload["points"], [])
        self.assertEqual(len(result.payload["rejected_citations"]), 1)
        self.assertTrue(result.is_error)


class TestDispatch(unittest.TestCase):
    def test_unknown_tool_is_an_error_not_a_crash(self):
        result = tools.execute("do_something_else", {})
        self.assertTrue(result.is_error)
        self.assertIn("Unknown tool", result.payload["error"])

    def test_handler_exception_is_returned_to_the_model(self):
        # A malformed findings list must not take down the run.
        result = tools.execute("check_clauses", {"findings": "not a list"})
        self.assertTrue(result.is_error)

    def test_every_schema_has_a_handler(self):
        for schema in tools.TOOL_SCHEMAS:
            with self.subTest(tool=schema["name"]):
                self.assertIn(schema["name"], tools.HANDLERS)

    def test_every_handler_has_a_schema(self):
        names = {s["name"] for s in tools.TOOL_SCHEMAS}
        self.assertEqual(set(tools.HANDLERS), names)


if __name__ == "__main__":
    unittest.main()
