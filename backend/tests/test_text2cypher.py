"""Tests for Text2Cypher (Mode D) pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Validation tests (no LLM/Neo4j needed) ────────────────────────

class TestValidateCypher:
    """Tests for Cypher safety validation."""

    def test_valid_match_return(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("MATCH (n:Customer) RETURN n.name")
        assert ok is True
        assert err is None

    def test_valid_complex_query(self):
        from app.query.text2cypher import validate_cypher

        cypher = (
            "MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product) "
            "WITH c, count(p) AS cnt "
            "RETURN c.name, cnt ORDER BY cnt DESC LIMIT 5"
        )
        ok, err = validate_cypher(cypher)
        assert ok is True

    def test_valid_optional_match(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher(
            "MATCH (c:Customer) OPTIONAL MATCH (c)-[:PLACED]->(o:Order) RETURN c.name, count(o)"
        )
        assert ok is True

    def test_rejects_delete(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("MATCH (n) DELETE n RETURN count(n)")
        assert ok is False
        assert "Write operations" in err

    def test_rejects_detach_delete(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("MATCH (n) DETACH DELETE n RETURN count(n)")
        assert ok is False

    def test_rejects_create(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("CREATE (n:Test {name: 'bad'}) RETURN n")
        assert ok is False

    def test_rejects_merge(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("MERGE (n:Test {name: 'bad'}) RETURN n")
        assert ok is False

    def test_rejects_set(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("MATCH (n:Customer) SET n.name = 'hacked' RETURN n")
        assert ok is False

    def test_rejects_drop(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("MATCH (n) RETURN n; DROP INDEX idx_name")
        assert ok is False  # Multiple statements or DROP

    def test_rejects_load_csv(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher(
            "LOAD CSV FROM 'file:///evil.csv' AS row MATCH (n) RETURN n"
        )
        assert ok is False

    def test_requires_return(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("MATCH (n:Customer)")
        assert ok is False
        assert "RETURN" in err

    def test_requires_match(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("RETURN 1 AS num")
        assert ok is False
        assert "MATCH" in err

    def test_max_length(self):
        from app.query.text2cypher import validate_cypher

        long_cypher = "MATCH (n) RETURN n " + " " * 2000
        ok, err = validate_cypher(long_cypher)
        assert ok is False
        assert "maximum length" in err

    def test_no_semicolons(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher(
            "MATCH (n) RETURN n; MATCH (m) RETURN m"
        )
        assert ok is False
        assert "Multiple statements" in err

    def test_empty_cypher(self):
        from app.query.text2cypher import validate_cypher

        ok, err = validate_cypher("")
        assert ok is False

    def test_allows_case_expression(self):
        """CASE expressions should NOT be blocked."""
        from app.query.text2cypher import validate_cypher

        cypher = (
            "MATCH (o:Order) "
            "RETURN CASE WHEN o.amount > 100 THEN 'high' ELSE 'low' END AS level, count(o)"
        )
        ok, err = validate_cypher(cypher)
        assert ok is True


class TestStripMarkdownFences:
    def test_strips_backtick_fences(self):
        from app.query.text2cypher import _strip_markdown_fences

        result = _strip_markdown_fences("```cypher\nMATCH (n) RETURN n\n```")
        assert result == "MATCH (n) RETURN n"

    def test_no_fences(self):
        from app.query.text2cypher import _strip_markdown_fences

        result = _strip_markdown_fences("MATCH (n) RETURN n")
        assert result == "MATCH (n) RETURN n"


# ── Pipeline tests (mocked LLM + Neo4j) ───────────────────────────

class TestText2CypherPipeline:

    @patch("app.query.text2cypher.get_driver")
    @patch("app.query.text2cypher.call_llm")
    @patch("app.query.text2cypher.get_graph_schema")
    @patch("app.query.text2cypher.has_any_api_key", return_value=True)
    def test_happy_path(self, mock_key, mock_schema, mock_llm, mock_driver):
        from app.llm.provider import LLMResponse
        from app.query.text2cypher import run_text2cypher_query

        mock_schema.return_value = {
            "node_labels": ["Customer", "Order"],
            "relationship_types": ["PLACED"],
            "node_properties": {"Customer": ["id", "name"]},
            "relationship_properties": {},
        }

        # First call: generate cypher
        gen_resp = LLMResponse(
            text="MATCH (c:Customer) RETURN c.name AS name",
            model="gpt-4o", input_tokens=100, output_tokens=20,
        )
        # Second call: synthesize answer
        ans_resp = LLMResponse(
            text="고객 목록: 김민수, 이영희",
            model="gpt-4o", input_tokens=150, output_tokens=30,
        )
        mock_llm.side_effect = [gen_resp, ans_resp]

        # Mock Neo4j
        mock_session = MagicMock()
        mock_result = [{"name": "김민수"}, {"name": "이영희"}]
        mock_session.run.return_value = mock_result
        mock_driver.return_value.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.return_value.session.return_value.__exit__ = MagicMock(return_value=False)

        result = run_text2cypher_query("고객 목록을 보여줘")

        assert result.mode == "d"
        assert result.route == "text2cypher"
        assert result.matched_by == "llm_cypher"
        assert result.error is None
        assert result.cypher == "MATCH (c:Customer) RETURN c.name AS name"
        assert "김민수" in result.answer
        assert result.llm_tokens_used > 0

    @patch("app.query.text2cypher.call_llm")
    @patch("app.query.text2cypher.get_graph_schema")
    @patch("app.query.text2cypher.has_any_api_key", return_value=True)
    def test_invalid_cypher_from_llm(self, mock_key, mock_schema, mock_llm):
        from app.llm.provider import LLMResponse
        from app.query.text2cypher import run_text2cypher_query

        mock_schema.return_value = {
            "node_labels": ["Customer"],
            "relationship_types": [],
            "node_properties": {"Customer": ["id", "name"]},
            "relationship_properties": {},
        }
        # LLM generates destructive query
        mock_llm.return_value = LLMResponse(
            text="MATCH (n) DETACH DELETE n",
            model="gpt-4o", input_tokens=100, output_tokens=10,
        )

        result = run_text2cypher_query("Delete everything")
        assert result.error is not None
        assert "validation_failed" in result.error
        assert result.cypher == "MATCH (n) DETACH DELETE n"

    @patch("app.query.text2cypher.has_any_api_key", return_value=False)
    def test_no_api_key(self, mock_key):
        from app.query.text2cypher import run_text2cypher_query

        result = run_text2cypher_query("What customers?")
        assert result.error == "no_api_key"
        assert result.mode == "d"

    @patch("app.query.text2cypher.get_graph_schema")
    @patch("app.query.text2cypher.has_any_api_key", return_value=True)
    def test_empty_schema(self, mock_key, mock_schema):
        from app.query.text2cypher import run_text2cypher_query

        mock_schema.return_value = {
            "node_labels": [],
            "relationship_types": [],
            "node_properties": {},
            "relationship_properties": {},
        }

        result = run_text2cypher_query("What customers?")
        assert result.error == "empty_schema"

    @patch("app.query.text2cypher.call_llm")
    @patch("app.query.text2cypher.get_graph_schema")
    @patch("app.query.text2cypher.has_any_api_key", return_value=True)
    def test_llm_generation_failure(self, mock_key, mock_schema, mock_llm):
        from app.query.text2cypher import run_text2cypher_query

        mock_schema.return_value = {
            "node_labels": ["Customer"],
            "relationship_types": [],
            "node_properties": {},
            "relationship_properties": {},
        }
        mock_llm.return_value = None  # LLM fails

        result = run_text2cypher_query("Give me customers")
        assert result.error == "llm_generation_failed"

    @patch("app.query.text2cypher.get_driver")
    @patch("app.query.text2cypher.call_llm")
    @patch("app.query.text2cypher.get_graph_schema")
    @patch("app.query.text2cypher.has_any_api_key", return_value=True)
    def test_neo4j_execution_failure(self, mock_key, mock_schema, mock_llm, mock_driver):
        from app.llm.provider import LLMResponse
        from app.query.text2cypher import run_text2cypher_query

        mock_schema.return_value = {
            "node_labels": ["Customer"],
            "relationship_types": [],
            "node_properties": {},
            "relationship_properties": {},
        }
        mock_llm.return_value = LLMResponse(
            text="MATCH (c:Customer) RETURN c.name",
            model="gpt-4o", input_tokens=100, output_tokens=10,
        )

        # Neo4j raises error
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Connection refused")
        mock_driver.return_value.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.return_value.session.return_value.__exit__ = MagicMock(return_value=False)

        result = run_text2cypher_query("Show customers")
        assert result.error is not None
        assert "execution_failed" in result.error


# ── API endpoint tests ────────────────────────────────────────────

class TestQueryEndpointModeD:

    @patch("app.query.text2cypher.get_driver")
    @patch("app.query.text2cypher.call_llm")
    @patch("app.query.text2cypher.get_graph_schema")
    @patch("app.query.text2cypher.has_any_api_key", return_value=True)
    def test_mode_d_endpoint(self, mock_key, mock_schema, mock_llm, mock_driver):
        from app.llm.provider import LLMResponse
        from app.main import create_app

        app = create_app()
        client = TestClient(app)

        mock_schema.return_value = {
            "node_labels": ["Customer"],
            "relationship_types": [],
            "node_properties": {"Customer": ["id", "name"]},
            "relationship_properties": {},
        }
        gen_resp = LLMResponse(
            text="MATCH (c:Customer) RETURN c.name AS name",
            model="gpt-4o", input_tokens=100, output_tokens=20,
        )
        ans_resp = LLMResponse(
            text="고객: 김민수",
            model="gpt-4o", input_tokens=150, output_tokens=10,
        )
        mock_llm.side_effect = [gen_resp, ans_resp]

        mock_session = MagicMock()
        mock_session.run.return_value = [{"name": "김민수"}]
        mock_driver.return_value.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.return_value.session.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.post("/api/v1/query", json={
            "question": "고객 목록",
            "mode": "d",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "d"
        assert data["route"] == "text2cypher"


class TestPrompts:
    """Tests for prompt building functions."""

    def test_build_cypher_messages(self):
        from app.query.text2cypher_prompts import build_cypher_messages

        messages = build_cypher_messages("Who are the customers?", "Node types: Customer")
        # Few-shot (4 pairs = 8 messages) + 1 actual question = 9
        assert len(messages) == 9
        assert messages[-1]["role"] == "user"
        assert "Who are the customers?" in messages[-1]["content"]

    def test_build_answer_messages(self):
        from app.query.text2cypher_prompts import build_answer_messages

        messages = build_answer_messages(
            "Show customers",
            "MATCH (c:Customer) RETURN c.name",
            [{"name": "Kim"}, {"name": "Lee"}],
        )
        assert len(messages) == 1
        assert "Show customers" in messages[0]["content"]
        assert "Kim" in messages[0]["content"]

    def test_answer_messages_truncation(self):
        from app.query.text2cypher_prompts import build_answer_messages

        # 50 results, should truncate to 20
        results = [{"n": i} for i in range(50)]
        messages = build_answer_messages("test", "MATCH (n) RETURN n", results, max_results=20)
        assert "50 total" in messages[0]["content"]
        assert "showing first 20" in messages[0]["content"]
