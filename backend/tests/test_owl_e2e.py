"""OWL E2E 통합 테스트."""

from __future__ import annotations

import pytest
from rdflib.namespace import OWL, RDF

from app.models.schemas import ERDSchema
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import ontology_to_owl, owl_to_ontology, serialize_owl
from app.owl.reasoner import run_reasoning
from app.owl.shacl_generator import generate_shapes
from app.owl.shacl_validator import validate_shacl


def test_e2e_full_pipeline(ecommerce_erd: ERDSchema):
    """#1: DDL → 온톨로지 → OWL → 추론 → SHACL → round-trip → 직렬화."""
    ontology = build_ontology(ecommerce_erd)
    assert len(ontology.node_types) == 9

    g = ontology_to_owl(ontology, domain="ecommerce")
    assert sum(1 for _ in g.subjects(RDF.type, OWL.Class)) == 9

    result = run_reasoning(g, domain="ecommerce")
    assert result.axioms_applied >= 3
    assert "PARENT_OF" in result.transitive_rels

    shapes = generate_shapes(ontology)
    conforms, issues = validate_shacl(g, shapes)
    assert isinstance(conforms, bool)

    restored = owl_to_ontology(g)
    assert len(restored.node_types) >= len(ontology.node_types)

    turtle = serialize_owl(g, "turtle")
    assert "TransitiveProperty" in turtle


def test_e2e_without_owl_flag(ecommerce_erd: ERDSchema):
    """#2: enable_owl=False → 기존 파이프라인만 동작."""
    from app.ontology.pipeline import generate_ontology
    response = generate_ontology(ecommerce_erd, skip_llm=True)
    assert response.ontology is not None
    assert len(response.ontology.node_types) == 9


def test_e2e_education_pipeline():
    """#3: Education 도메인 E2E."""
    from pathlib import Path
    ddl_path = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas" / "demo_education.sql"
    if not ddl_path.exists():
        pytest.skip("Education DDL not found")
    from app.ddl_parser.parser import parse_ddl
    erd = parse_ddl(ddl_path.read_text(encoding="utf-8"))
    ontology = build_ontology(erd)
    g = ontology_to_owl(ontology, domain="education")
    result = run_reasoning(g, domain="education")
    assert result.axioms_applied >= 2
    assert "REQUIRES" in result.transitive_rels
