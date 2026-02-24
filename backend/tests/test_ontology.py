"""Ontology unit + integration tests — 16 cases."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.pg_client import compute_erd_hash
from app.evaluation.evaluator import evaluate
from app.evaluation.golden_ecommerce import (
    GOLDEN_NODE_NAMES,
    GOLDEN_RELATIONSHIP_SPECS,
)
from app.main import create_app
from app.models.schemas import ERDSchema, OntologySpec, RelationshipType
from app.ontology.fk_rule_engine import build_ontology


# ════════════════════════════════════════════════════════════════════
#  FK Engine Tests (1–7)
# ════════════════════════════════════════════════════════════════════


def test_fk_engine_node_count(ecommerce_erd: ERDSchema):
    """#1: FK engine produces exactly 9 node types."""
    ontology = build_ontology(ecommerce_erd)
    assert len(ontology.node_types) == 9


def test_fk_engine_relationship_count(ecommerce_erd: ERDSchema):
    """#2: FK engine produces exactly 12 relationship types."""
    ontology = build_ontology(ecommerce_erd)
    assert len(ontology.relationship_types) == 12


def test_fk_engine_derivation_tags(ecommerce_erd: ERDSchema):
    """#3: 9 fk_direct + 3 fk_join_table derivation tags."""
    ontology = build_ontology(ecommerce_erd)
    direct = [r for r in ontology.relationship_types if r.derivation == "fk_direct"]
    join = [r for r in ontology.relationship_types if r.derivation == "fk_join_table"]
    assert len(direct) == 9
    assert len(join) == 3


def test_fk_engine_direction_accuracy(ecommerce_erd: ERDSchema):
    """#4: All 12 relationship directions match golden data."""
    ontology = build_ontology(ecommerce_erd)
    gen_map = {r.name: (r.source_node, r.target_node) for r in ontology.relationship_types}

    for name, src, tgt, _ in GOLDEN_RELATIONSHIP_SPECS:
        assert name in gen_map, f"Missing relationship: {name}"
        assert gen_map[name] == (src, tgt), (
            f"{name}: expected ({src}, {tgt}), got {gen_map[name]}"
        )


def test_fk_engine_node_names(ecommerce_erd: ERDSchema):
    """#5: Exact node name set matches golden data."""
    ontology = build_ontology(ecommerce_erd)
    gen_names = {n.name for n in ontology.node_types}
    assert gen_names == GOLDEN_NODE_NAMES


def test_fk_engine_relationship_names(ecommerce_erd: ERDSchema):
    """#6: Exact relationship name set matches golden data."""
    ontology = build_ontology(ecommerce_erd)
    gen_names = {r.name for r in ontology.relationship_types}
    golden_names = {name for name, _, _, _ in GOLDEN_RELATIONSHIP_SPECS}
    assert gen_names == golden_names


def test_fk_engine_join_table_properties(ecommerce_erd: ERDSchema):
    """#7: Join-table relationships carry the correct properties."""
    ontology = build_ontology(ecommerce_erd)
    rel_map = {r.name: r for r in ontology.relationship_types}

    # CONTAINS → quantity, unit_price
    contains = rel_map["CONTAINS"]
    contains_props = {p.name for p in contains.properties}
    assert "quantity" in contains_props
    assert "unit_price" in contains_props

    # SHIPPED_TO → carrier, tracking_number, status
    shipped = rel_map["SHIPPED_TO"]
    shipped_props = {p.name for p in shipped.properties}
    assert "carrier" in shipped_props
    assert "tracking_number" in shipped_props
    assert "status" in shipped_props

    # WISHLISTED → no properties
    wishlisted = rel_map["WISHLISTED"]
    assert len(wishlisted.properties) == 0


# ════════════════════════════════════════════════════════════════════
#  Evaluation Tests (8–10)
# ════════════════════════════════════════════════════════════════════


def test_eval_perfect_score(ecommerce_erd: ERDSchema):
    """#8: FK baseline achieves 0% error rate and 100% coverage."""
    ontology = build_ontology(ecommerce_erd)
    metrics = evaluate(ontology, GOLDEN_NODE_NAMES, GOLDEN_RELATIONSHIP_SPECS)
    assert metrics.critical_error_rate == 0.0
    assert metrics.fk_relationship_coverage == 1.0
    assert metrics.direction_accuracy == 1.0


def test_eval_missing_node(ecommerce_erd: ERDSchema):
    """#9: Removing a node increases critical error rate."""
    ontology = build_ontology(ecommerce_erd)
    # Remove the first node
    ontology.node_types = ontology.node_types[1:]
    metrics = evaluate(ontology, GOLDEN_NODE_NAMES, GOLDEN_RELATIONSHIP_SPECS)
    assert metrics.critical_error_rate > 0.0


def test_eval_wrong_direction(ecommerce_erd: ERDSchema):
    """#10: Flipping a direction decreases direction accuracy."""
    ontology = build_ontology(ecommerce_erd)
    # Find a non-self-referential relationship to flip
    idx = next(
        i for i, r in enumerate(ontology.relationship_types)
        if r.source_node != r.target_node
    )
    rel = ontology.relationship_types[idx]
    ontology.relationship_types[idx] = RelationshipType(
        name=rel.name,
        source_node=rel.target_node,  # flipped
        target_node=rel.source_node,  # flipped
        data_table=rel.data_table,
        source_key_column=rel.source_key_column,
        target_key_column=rel.target_key_column,
        properties=rel.properties,
        derivation=rel.derivation,
    )
    metrics = evaluate(ontology, GOLDEN_NODE_NAMES, GOLDEN_RELATIONSHIP_SPECS)
    assert metrics.direction_accuracy < 1.0


# ════════════════════════════════════════════════════════════════════
#  ERD Hash Tests (11–12)
# ════════════════════════════════════════════════════════════════════


def test_erd_hash_deterministic(ecommerce_erd: ERDSchema):
    """#11: Same ERD produces the same hash."""
    d = ecommerce_erd.model_dump()
    h1 = compute_erd_hash(d)
    h2 = compute_erd_hash(d)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_erd_hash_changes(ecommerce_erd: ERDSchema):
    """#12: Modified ERD produces a different hash."""
    d1 = ecommerce_erd.model_dump()
    d2 = ecommerce_erd.model_dump()
    d2["tables"].append({"name": "extra", "columns": [], "primary_key": None})
    assert compute_erd_hash(d1) != compute_erd_hash(d2)


# ════════════════════════════════════════════════════════════════════
#  API Integration Tests (13–16)
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def _app():
    return create_app()


@pytest.fixture
async def api_client(_app):
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_api_generate_fk_only(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#13: POST skip_llm=true → 200, 9 nodes, 12 rels, stage=fk_only."""
    body = {"erd": ecommerce_erd.model_dump(), "skip_llm": True}
    with patch("app.ontology.pipeline.save_version", return_value=None):
        resp = await api_client.post("/api/v1/ontology/generate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["ontology"]["node_types"]) == 9
    assert len(data["ontology"]["relationship_types"]) == 12
    assert data["stage"] == "fk_only"
    assert data["eval_report"]["critical_error_rate"] == 0.0


@pytest.mark.anyio
async def test_api_generate_empty_erd(api_client: AsyncClient):
    """#14: Empty ERD → 200, 0 nodes, 0 rels."""
    body = {"erd": {"tables": [], "foreign_keys": []}, "skip_llm": True}
    with patch("app.ontology.pipeline.save_version", return_value=None):
        resp = await api_client.post("/api/v1/ontology/generate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["ontology"]["node_types"]) == 0
    assert len(data["ontology"]["relationship_types"]) == 0


@pytest.mark.anyio
async def test_api_generate_invalid_body(api_client: AsyncClient):
    """#15: Invalid JSON body → 422."""
    resp = await api_client.post(
        "/api/v1/ontology/generate",
        json={"bad_field": "value"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_llm_skipped_no_key(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#16: No API key → stage=fk_only, llm_diffs=[]."""
    body = {"erd": ecommerce_erd.model_dump(), "skip_llm": False}
    with (
        patch("app.config.settings.anthropic_api_key", None),
        patch("app.ontology.pipeline.save_version", return_value=None),
    ):
        resp = await api_client.post("/api/v1/ontology/generate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stage"] == "fk_only"
    assert data["llm_diffs"] == []
