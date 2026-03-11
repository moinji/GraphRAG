"""OWL 쿼리 통합 테스트."""

from __future__ import annotations

from app.db.graph_schema import format_schema_for_prompt
from app.owl.schema_enricher import enrich_schema_with_owl
from app.models.schemas import ERDSchema
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import ontology_to_owl
from app.owl.reasoner import run_reasoning


def _make_enriched_schema(ecommerce_erd: ERDSchema) -> dict:
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    run_reasoning(g, domain="ecommerce")
    base_schema = {
        "node_labels": [nt.name for nt in ontology.node_types],
        "relationship_types": [rt.name for rt in ontology.relationship_types],
        "node_properties": {},
        "relationship_properties": {},
    }
    return enrich_schema_with_owl(base_schema, g)


def test_enriched_schema_has_transitive(ecommerce_erd: ERDSchema):
    """#1"""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "PARENT_OF" in schema["transitive_properties"]


def test_enriched_schema_has_inverse(ecommerce_erd: ERDSchema):
    """#2"""
    schema = _make_enriched_schema(ecommerce_erd)
    assert len(schema["inverse_pairs"]) >= 2


def test_enriched_schema_has_chains(ecommerce_erd: ERDSchema):
    """#3"""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "inferred_paths" in schema


def test_format_prompt_includes_owl(ecommerce_erd: ERDSchema):
    """#4"""
    schema = _make_enriched_schema(ecommerce_erd)
    prompt = format_schema_for_prompt(schema)
    assert "Transitive properties" in prompt
    assert "PARENT_OF" in prompt


def test_format_prompt_without_owl():
    """#5: OWL 없는 스키마 하위호환."""
    schema = {
        "node_labels": ["Customer", "Product"],
        "relationship_types": ["PLACED"],
        "node_properties": {"Customer": ["id", "name"]},
        "relationship_properties": {},
    }
    prompt = format_schema_for_prompt(schema)
    assert "Customer" in prompt
    assert "Transitive" not in prompt


def test_enriched_schema_preserves_base(ecommerce_erd: ERDSchema):
    """#6"""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "node_labels" in schema
    assert len(schema["node_labels"]) > 0
