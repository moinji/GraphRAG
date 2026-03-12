"""Tests for document NER (Named Entity Recognition)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.document.ner import (
    ExtractedEntity,
    _parse_llm_ner_response,
    extract_entities,
    _kg_match_ner,
    _llm_ner,
)


# ── ExtractedEntity dataclass ───────────────────────────────────

class TestExtractedEntity:
    def test_defaults(self):
        e = ExtractedEntity(name="Alice", label="Customer", confidence=1.0, source="kg_match")
        assert e.char_start == -1
        assert e.char_end == -1

    def test_with_positions(self):
        e = ExtractedEntity(
            name="Bob", label="Customer", confidence=0.9, source="llm",
            char_start=10, char_end=13,
        )
        assert e.char_start == 10
        assert e.char_end == 13


# ── _parse_llm_ner_response ────────────────────────────────────

class TestParseLlmNerResponse:
    def test_valid_json_array(self):
        raw = '[{"name": "Alice", "label": "Customer"}, {"name": "Widget", "label": "Product"}]'
        result = _parse_llm_ner_response(raw)
        assert len(result) == 2
        assert result[0].name == "Alice"
        assert result[0].confidence == 0.7
        assert result[0].source == "llm"

    def test_json_with_surrounding_text(self):
        raw = 'Here are the entities:\n[{"name": "Bob", "label": "Person"}]\nDone.'
        result = _parse_llm_ner_response(raw)
        assert len(result) == 1
        assert result[0].name == "Bob"

    def test_empty_response(self):
        assert _parse_llm_ner_response("") == []

    def test_no_json_array(self):
        assert _parse_llm_ner_response("no entities found") == []

    def test_invalid_json(self):
        assert _parse_llm_ner_response("[{invalid json}]") == []

    def test_missing_keys(self):
        raw = '[{"name": "Alice"}, {"label": "Foo"}]'
        result = _parse_llm_ner_response(raw)
        assert len(result) == 0  # both items missing required keys

    def test_mixed_valid_invalid(self):
        raw = '[{"name": "Alice", "label": "Customer"}, {"only_name": "Bob"}]'
        result = _parse_llm_ner_response(raw)
        assert len(result) == 1
        assert result[0].name == "Alice"


# ── _kg_match_ner ──────────────────────────────────────────────

class TestKgMatchNer:
    @patch("app.query.local_search._load_entities_from_neo4j", return_value={})
    def test_empty_kg(self, mock_load):
        """No entities in KG → empty results."""
        result = _kg_match_ner("some text about products")
        assert result == []

    @patch("app.query.local_search._load_entities_from_neo4j")
    def test_single_match(self, mock_load):
        mock_load.return_value = {"Customer": ["Alice", "Bob"]}
        result = _kg_match_ner("Alice ordered a widget")
        assert len(result) == 1
        assert result[0].name == "Alice"
        assert result[0].label == "Customer"
        assert result[0].confidence == 1.0
        assert result[0].source == "kg_match"
        assert result[0].char_start == 0

    @patch("app.query.local_search._load_entities_from_neo4j")
    def test_multiple_matches(self, mock_load):
        mock_load.return_value = {
            "Customer": ["Alice", "Bob"],
            "Product": ["Widget"],
        }
        result = _kg_match_ner("Alice bought a Widget and Bob bought one too")
        names = {e.name for e in result}
        assert "Alice" in names
        assert "Widget" in names
        assert "Bob" in names

    @patch("app.query.local_search._load_entities_from_neo4j")
    def test_case_insensitive(self, mock_load):
        mock_load.return_value = {"Product": ["Widget Pro"]}
        result = _kg_match_ner("I love my widget pro")
        assert len(result) == 1
        assert result[0].name == "Widget Pro"

    @patch("app.query.local_search._load_entities_from_neo4j")
    def test_sorted_by_position(self, mock_load):
        mock_load.return_value = {"Customer": ["Bob", "Alice"]}
        result = _kg_match_ner("Alice and Bob")
        assert result[0].name == "Alice"
        assert result[1].name == "Bob"

    @patch("app.query.local_search._load_entities_from_neo4j", side_effect=Exception("Neo4j down"))
    def test_neo4j_failure_returns_empty(self, mock_load):
        result = _kg_match_ner("any text")
        assert result == []


# ── extract_entities (integration) ─────────────────────────────

class TestExtractEntities:
    @patch("app.document.ner._kg_match_ner", return_value=[])
    @patch("app.document.ner.settings")
    def test_no_entities_no_api_key(self, mock_settings, mock_kg):
        """No KG matches, no API key → empty."""
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None
        result = extract_entities("some text")
        assert result == []

    @patch("app.document.ner._kg_match_ner")
    @patch("app.document.ner.settings")
    def test_kg_matches_returned(self, mock_settings, mock_kg):
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None
        mock_kg.return_value = [
            ExtractedEntity("Alice", "Customer", 1.0, "kg_match"),
            ExtractedEntity("Bob", "Customer", 1.0, "kg_match"),
            ExtractedEntity("Widget", "Product", 1.0, "kg_match"),
        ]
        result = extract_entities("text")
        assert len(result) == 3

    @patch("app.document.ner._llm_ner")
    @patch("app.document.ner._kg_match_ner", return_value=[])
    @patch("app.document.ner.settings")
    def test_llm_fallback_when_few_kg_matches(self, mock_settings, mock_kg, mock_llm):
        """LLM NER called when < 3 KG matches and API key exists."""
        mock_settings.openai_api_key = "sk-test"
        mock_settings.anthropic_api_key = None
        mock_llm.return_value = [
            ExtractedEntity("NewEntity", "Organization", 0.7, "llm"),
        ]
        result = extract_entities("text about NewEntity")
        assert len(result) == 1
        assert result[0].source == "llm"

    @patch("app.document.ner._llm_ner", side_effect=Exception("LLM failed"))
    @patch("app.document.ner._kg_match_ner", return_value=[])
    @patch("app.document.ner.settings")
    def test_llm_failure_non_fatal(self, mock_settings, mock_kg, mock_llm):
        """LLM failure is non-fatal — returns whatever KG found."""
        mock_settings.openai_api_key = "sk-test"
        mock_settings.anthropic_api_key = None
        result = extract_entities("text")
        assert result == []

    @patch("app.document.ner._kg_match_ner")
    @patch("app.document.ner.settings")
    def test_deduplication(self, mock_settings, mock_kg):
        """Duplicate (name, label) pairs are deduplicated."""
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None
        mock_kg.return_value = [
            ExtractedEntity("Alice", "Customer", 1.0, "kg_match"),
            ExtractedEntity("Alice", "Customer", 1.0, "kg_match"),
        ]
        result = extract_entities("text")
        assert len(result) == 1

    @patch("app.document.ner._kg_match_ner")
    @patch("app.document.ner.settings")
    def test_max_entities_limit(self, mock_settings, mock_kg):
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None
        mock_kg.return_value = [
            ExtractedEntity(f"Entity{i}", "Label", 1.0, "kg_match")
            for i in range(30)
        ]
        result = extract_entities("text", max_entities=5)
        assert len(result) == 5

    @patch("app.document.ner._llm_ner")
    @patch("app.document.ner._kg_match_ner")
    @patch("app.document.ner.settings")
    def test_llm_not_called_when_enough_kg_matches(self, mock_settings, mock_kg, mock_llm):
        """LLM NER skipped when >= 3 KG matches."""
        mock_settings.openai_api_key = "sk-test"
        mock_kg.return_value = [
            ExtractedEntity("A", "X", 1.0, "kg_match"),
            ExtractedEntity("B", "Y", 1.0, "kg_match"),
            ExtractedEntity("C", "Z", 1.0, "kg_match"),
        ]
        result = extract_entities("text")
        assert len(result) == 3
        mock_llm.assert_not_called()
