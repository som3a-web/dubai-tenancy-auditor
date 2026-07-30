"""Tests for configuration and the API key sanity check.

The key check exists because a placeholder pasted verbatim into Streamlit
secrets looks identical to a working setup until the first API call fails with
an opaque 401, several clicks into a demo. Catching it at page load is worth a
few tests.

No test here contains or prints real key material.
"""

from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REAL_SHAPED_KEY = "sk-ant-" + "a" * 95


class KeyStatusCase(unittest.TestCase):
    """Reload config per case so the env var is re-read."""

    def status_for(self, value: str | None) -> tuple[str, str]:
        if value is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = value
        import src.config as config

        importlib.reload(config)
        return config.api_key_status()

    def tearDown(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        import src.config as config

        importlib.reload(config)


class TestApiKeyStatus(KeyStatusCase):
    def test_missing(self):
        status, message = self.status_for(None)
        self.assertEqual(status, "missing")
        self.assertIn("No ANTHROPIC_API_KEY", message)

    def test_placeholder_pasted_literally_is_caught(self):
        # The exact string from the setup instructions.
        status, message = self.status_for("sk-ant-...")
        self.assertEqual(status, "malformed")
        self.assertIn("placeholder", message)

    def test_wrong_value_entirely_is_caught(self):
        status, message = self.status_for("my-api-key")
        self.assertEqual(status, "malformed")
        self.assertIn("sk-ant-", message)

    def test_empty_string_is_missing_not_malformed(self):
        status, _ = self.status_for("")
        self.assertEqual(status, "missing")

    def test_real_shaped_key_is_present(self):
        status, _ = self.status_for(REAL_SHAPED_KEY)
        self.assertEqual(status, "present")

    def test_stray_quotes_and_whitespace_are_stripped(self):
        # A frequent and otherwise baffling source of 401s.
        status, _ = self.status_for(f'  "{REAL_SHAPED_KEY}"  ')
        self.assertEqual(status, "present")

    def test_status_never_leaks_key_material(self):
        _, message = self.status_for(REAL_SHAPED_KEY)
        self.assertNotIn(REAL_SHAPED_KEY, message)
        self.assertNotIn("aaaa", message)

    def test_present_does_not_claim_the_api_accepted_it(self):
        """'present' must describe shape, not validity — only a request proves that."""
        _, message = self.status_for(REAL_SHAPED_KEY)
        self.assertIn("shape", message.lower())


class TestCeilings(KeyStatusCase):
    def test_defaults_are_sane(self):
        import src.config as config

        importlib.reload(config)
        self.assertGreater(config.max_tokens_per_run(), 0)
        self.assertGreater(config.max_agent_iterations(), 0)

    def test_non_numeric_override_falls_back_to_default(self):
        os.environ["MAX_AGENT_ITERATIONS"] = "not a number"
        import src.config as config

        importlib.reload(config)
        try:
            self.assertEqual(
                config.max_agent_iterations(), config.DEFAULT_MAX_AGENT_ITERATIONS
            )
        finally:
            os.environ.pop("MAX_AGENT_ITERATIONS", None)


if __name__ == "__main__":
    unittest.main()
