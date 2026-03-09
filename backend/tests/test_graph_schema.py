"""Graph schema introspection + domain-agnostic query routing tests — 12 cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.db.graph_schema import (
    format_schema_for_prompt,
    get_graph_schema,
    invalidate_schema_cache,
)


# ════════════════════════════════════════════════════════════════════
#  Schema Introspection (1–4)
# ════════════════════════════════════════════════════════════════════


def test_schema_empty_on_failure():
    """#1: Schema returns empty structure when Neo4j is unavailable."""
    invalidate_schema_cache()
    with patch("app.db.neo4j_client.get_driver", side_effect=Exception("No connection")):
        schema = get_graph_schema()
    assert schema["node_labels"] == []
    assert schema["relationship_types"] == []
    assert schema["node_properties"] == {}


def test_schema_caching():
    """#2: Schema is cached and returned on subsequent calls."""
    invalidate_schema_cache()

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # Simulate db.labels() call
    label_records = [{"label": "Student"}, {"label": "Course"}]
    rel_records = [{"relationshipType": "ENROLLED_IN"}]
    prop_records_student = [{"props": ["id", "name", "email"]}]
    prop_records_course = [{"props": ["id", "title"]}]
    rel_prop_records = []

    call_count = 0

    def mock_run(cypher, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if "db.labels()" in cypher:
            result.__iter__ = MagicMock(return_value=iter(label_records))
        elif "db.relationshipTypes()" in cypher:
            result.__iter__ = MagicMock(return_value=iter(rel_records))
        elif "Student" in cypher and "keys" in cypher:
            result.__iter__ = MagicMock(return_value=iter(prop_records_student))
        elif "Course" in cypher and "keys" in cypher:
            result.__iter__ = MagicMock(return_value=iter(prop_records_course))
        elif "ENROLLED_IN" in cypher:
            result.__iter__ = MagicMock(return_value=iter(rel_prop_records))
        else:
            result.__iter__ = MagicMock(return_value=iter([]))
        return result

    mock_session.run = mock_run
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.neo4j_client.get_driver", return_value=mock_driver):
        schema1 = get_graph_schema()
        first_call_count = call_count
        schema2 = get_graph_schema()

    assert set(schema1["node_labels"]) == {"Course", "Student"}
    assert schema1["relationship_types"] == ["ENROLLED_IN"]
    # Second call should be cached (no additional Neo4j calls)
    assert call_count == first_call_count


def test_schema_invalidation():
    """#3: Cache invalidation forces re-query."""
    invalidate_schema_cache()

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    def mock_run(cypher, **kwargs):
        result = MagicMock()
        if "db.labels()" in cypher:
            result.__iter__ = MagicMock(return_value=iter([{"label": "X"}]))
        elif "db.relationshipTypes()" in cypher:
            result.__iter__ = MagicMock(return_value=iter([]))
        elif "keys" in cypher:
            result.__iter__ = MagicMock(return_value=iter([{"props": ["id"]}]))
        else:
            result.__iter__ = MagicMock(return_value=iter([]))
        return result

    mock_session.run = mock_run
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.neo4j_client.get_driver", return_value=mock_driver):
        schema = get_graph_schema()
        assert schema["node_labels"] == ["X"]
        invalidate_schema_cache()
        # After invalidation, should re-query
        schema2 = get_graph_schema()
        assert schema2["node_labels"] == ["X"]


def test_schema_tenant_prefix():
    """#4: Tenant-prefixed labels are stripped correctly."""
    invalidate_schema_cache()

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    def mock_run(cypher, **kwargs):
        result = MagicMock()
        if "db.labels()" in cypher:
            result.__iter__ = MagicMock(return_value=iter([
                {"label": "T1__Student"},
                {"label": "T1__Course"},
                {"label": "OtherTenant__X"},
            ]))
        elif "db.relationshipTypes()" in cypher:
            result.__iter__ = MagicMock(return_value=iter([{"relationshipType": "ENROLLED_IN"}]))
        elif "keys" in cypher:
            result.__iter__ = MagicMock(return_value=iter([{"props": ["id"]}]))
        else:
            result.__iter__ = MagicMock(return_value=iter([]))
        return result

    mock_session.run = mock_run
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with (
        patch("app.db.neo4j_client.get_driver", return_value=mock_driver),
        patch("app.tenant.tenant_label_prefix", return_value="T1__"),
    ):
        schema = get_graph_schema(tenant_id="T1")

    assert "Student" in schema["node_labels"]
    assert "Course" in schema["node_labels"]
    # OtherTenant label should be excluded
    assert "X" not in schema["node_labels"]


# ════════════════════════════════════════════════════════════════════
#  Schema Formatting (5–7)
# ════════════════════════════════════════════════════════════════════


def test_format_empty_schema():
    """#5: Empty schema returns fallback message."""
    text = format_schema_for_prompt({"node_labels": [], "relationship_types": []})
    assert "No graph data loaded" in text


def test_format_basic_schema():
    """#6: Basic schema formatted correctly."""
    schema = {
        "node_labels": ["Student", "Course"],
        "relationship_types": ["ENROLLED_IN"],
        "node_properties": {"Student": ["id", "name"], "Course": ["id", "title"]},
        "relationship_properties": {},
    }
    text = format_schema_for_prompt(schema)
    assert "Student" in text
    assert "Course" in text
    assert "ENROLLED_IN" in text
    assert "Node properties:" in text


def test_format_with_rel_properties():
    """#7: Relationship properties included in formatted output."""
    schema = {
        "node_labels": ["Order", "Product"],
        "relationship_types": ["CONTAINS"],
        "node_properties": {},
        "relationship_properties": {"CONTAINS": ["quantity", "unit_price"]},
    }
    text = format_schema_for_prompt(schema)
    assert "Relationship properties:" in text
    assert "quantity" in text


# ════════════════════════════════════════════════════════════════════
#  Schema-Aware LLM Router (8–10)
# ════════════════════════════════════════════════════════════════════


def test_llm_router_uses_schema():
    """#8: LLM router system prompt includes dynamic schema."""
    from app.query.router_llm import _SYSTEM_PROMPT

    # The prompt should have {schema} placeholder
    assert "{schema}" in _SYSTEM_PROMPT


def test_llm_router_no_api_key():
    """#9: LLM router returns None without API key."""
    from app.query.router_llm import classify_by_llm

    with patch("app.query.router_llm.settings") as mock_settings:
        mock_settings.openai_api_key = ""
        mock_settings.anthropic_api_key = ""
        result = classify_by_llm("학생 김민수의 수강과목은?")
    assert result is None


def test_classify_by_llm_accepts_tenant_id():
    """#10: classify_by_llm accepts tenant_id parameter."""
    import inspect
    from app.query.router_llm import classify_by_llm

    sig = inspect.signature(classify_by_llm)
    assert "tenant_id" in sig.parameters


# ════════════════════════════════════════════════════════════════════
#  Domain-Agnostic Local Search (11–12)
# ════════════════════════════════════════════════════════════════════


def test_fallback_entities_empty():
    """#11: Fallback entities are empty (domain-agnostic)."""
    from app.query.local_search import _FALLBACK_ENTITIES

    assert _FALLBACK_ENTITIES == {}


def test_generic_aggregate_fallback():
    """#12: Generic aggregate Cypher generated from schema."""
    from app.query.local_search import _build_generic_aggregate

    schema = {
        "node_labels": ["Student", "Course"],
        "relationship_types": ["ENROLLED_IN"],
        "node_properties": {},
        "relationship_properties": {},
    }
    with patch("app.db.graph_schema.get_graph_schema", return_value=schema):
        cypher = _build_generic_aggregate()
    assert cypher is not None
    assert "ENROLLED_IN" in cypher
