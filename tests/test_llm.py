"""Tests for provider selection and schema translation.

No network calls. Backends are constructed with dummy keys only where that does
not trigger a request.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import llm, tools  # noqa: E402


class TestGeminiSchemaTranslation(unittest.TestCase):
    """Gemini rejects JSON Schema type arrays; the tool schemas use them."""

    def test_nullable_union_collapses_to_concrete_type(self):
        out = llm.to_gemini_schema({"type": ["string", "null"]})
        self.assertEqual(out["type"], "string")

    def test_number_union_collapses(self):
        out = llm.to_gemini_schema({"type": ["number", "null"]})
        self.assertEqual(out["type"], "number")

    def test_plain_types_untouched(self):
        out = llm.to_gemini_schema({"type": "string", "description": "x"})
        self.assertEqual(out, {"type": "string", "description": "x"})

    def test_nested_properties_are_translated(self):
        out = llm.to_gemini_schema(
            {
                "type": "object",
                "properties": {
                    "a": {"type": ["string", "null"]},
                    "b": {"type": "object", "properties": {"c": {"type": ["number", "null"]}}},
                },
                "required": ["a"],
            }
        )
        self.assertEqual(out["properties"]["a"]["type"], "string")
        self.assertEqual(out["properties"]["b"]["properties"]["c"]["type"], "number")

    def test_array_items_are_translated(self):
        out = llm.to_gemini_schema(
            {"type": "array", "items": {"type": "object",
                                        "properties": {"x": {"type": ["string", "null"]}}}}
        )
        self.assertEqual(out["items"]["properties"]["x"]["type"], "string")

    def test_required_and_enum_lists_are_preserved(self):
        out = llm.to_gemini_schema(
            {"type": "object", "required": ["a", "b"],
             "properties": {"s": {"type": "string", "enum": ["x", "y"]}}}
        )
        self.assertEqual(out["required"], ["a", "b"])
        self.assertEqual(out["properties"]["s"]["enum"], ["x", "y"])

    def test_every_real_tool_schema_survives_translation(self):
        """No type arrays may remain anywhere, at any depth."""

        def find_type_arrays(node, path="root"):
            problems = []
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "type" and isinstance(value, list):
                        problems.append(f"{path}.type = {value}")
                    else:
                        problems += find_type_arrays(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    problems += find_type_arrays(value, f"{path}[{i}]")
            return problems

        for schema in tools.TOOL_SCHEMAS:
            with self.subTest(tool=schema["name"]):
                translated = llm.to_gemini_schema(schema["input_schema"])
                self.assertEqual(find_type_arrays(translated), [])

    def test_translation_does_not_mutate_the_original(self):
        original = {"type": ["string", "null"]}
        llm.to_gemini_schema(original)
        self.assertEqual(original["type"], ["string", "null"])

    def test_optional_fields_stay_out_of_required(self):
        """Collapsing the union must not accidentally make a field mandatory."""
        for schema in tools.TOOL_SCHEMAS:
            before = set(schema["input_schema"].get("required", []))
            after = set(llm.to_gemini_schema(schema["input_schema"]).get("required", []))
            with self.subTest(tool=schema["name"]):
                self.assertEqual(before, after)


KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER")


class TestBackendSelection(unittest.TestCase):
    """Credential selection, isolated from the developer's real secrets.

    config._secret() reads Streamlit secrets before the environment, so clearing
    env vars alone does NOT give a clean slate — a real .streamlit/secrets.toml
    on the machine would leak in and make "no keys configured" untestable. These
    tests patch that seam so they assert on their own inputs only.
    """

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in KEY_VARS}
        import src.config as config

        self._patch = mock.patch.object(
            config, "_secret", side_effect=lambda name: os.environ.get(name)
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        for key in KEY_VARS:
            os.environ.pop(key, None)
        for key, value in self._saved.items():
            if value is not None:
                os.environ[key] = value

    def build(self):
        return llm.build_backend(tools.TOOL_SCHEMAS)

    def test_no_keys_returns_no_backend_with_guidance(self):
        backend, message = self.build()
        self.assertIsNone(backend)
        self.assertIn("GEMINI_API_KEY", message)

    def test_malformed_anthropic_key_is_explained_not_used(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..."
        backend, message = self.build()
        self.assertIsNone(backend)
        self.assertIn("placeholder", message)

    def test_gemini_key_alone_selects_gemini(self):
        os.environ["GEMINI_API_KEY"] = "AIza-test-key-not-real"
        backend, message = self.build()
        self.assertIsNotNone(backend)
        self.assertEqual(backend.name, "gemini")
        self.assertIn("Gemini", message)

    def test_google_api_key_is_accepted_as_an_alias(self):
        os.environ["GOOGLE_API_KEY"] = "AIza-test-key-not-real"
        backend, _ = self.build()
        self.assertIsNotNone(backend)
        self.assertEqual(backend.name, "gemini")

    def test_gemini_preferred_when_both_present(self):
        """Free tier first: it is the configuration that needs no billing."""
        os.environ["GEMINI_API_KEY"] = "AIza-test-key-not-real"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-" + "a" * 95
        backend, _ = self.build()
        self.assertEqual(backend.name, "gemini")

    def test_explicit_provider_override_wins(self):
        os.environ["GEMINI_API_KEY"] = "AIza-test-key-not-real"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-" + "a" * 95
        os.environ["LLM_PROVIDER"] = "anthropic"
        backend, _ = self.build()
        self.assertEqual(backend.name, "anthropic")


if __name__ == "__main__":
    unittest.main()
