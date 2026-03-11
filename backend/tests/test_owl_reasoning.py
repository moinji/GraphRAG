"""OWL 추론 + axiom 테스트."""

from __future__ import annotations

import pytest
from rdflib.namespace import OWL, RDF

from app.models.schemas import ERDSchema, OntologySpec
from app.ontology.fk_rule_engine import build_ontology
from app.owl.axiom_registry import ECOMMERCE_AXIOMS, AxiomSpec, apply_axioms, get_axioms
from app.owl.converter import GRAPHRAG, ontology_to_owl
from app.owl.reasoner import run_reasoning


def test_get_axioms_ecommerce():
    """#1: E-commerce axiom 조회."""
    axioms = get_axioms("ecommerce")
    assert len(axioms) >= 3
    types = {a.axiom_type for a in axioms}
    assert "TransitiveProperty" in types
    assert "inverseOf" in types


def test_get_axioms_unknown():
    """#2: 미등록 도메인 → 빈 리스트."""
    assert get_axioms("unknown_domain") == []


def test_apply_transitive(ecommerce_erd: ERDSchema):
    """#3: TransitiveProperty axiom 적용."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    apply_axioms(g, [AxiomSpec("PARENT_OF", "TransitiveProperty", "", domain="Category", range_cls="Category")])
    assert (GRAPHRAG["PARENT_OF"], RDF.type, OWL.TransitiveProperty) in g


def test_apply_inverse(ecommerce_erd: ERDSchema):
    """#4: inverseOf axiom 적용."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    apply_axioms(g, [AxiomSpec("PLACED", "inverseOf", "PLACED_BY")])
    assert (GRAPHRAG["PLACED"], OWL.inverseOf, GRAPHRAG["PLACED_BY"]) in g


def test_apply_property_chain(ecommerce_erd: ERDSchema):
    """#5: propertyChain axiom 적용."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    apply_axioms(g, [AxiomSpec("CUSTOMER_CATEGORY", "propertyChain", ["PLACED", "CONTAINS", "BELONGS_TO"])])
    assert (GRAPHRAG["CUSTOMER_CATEGORY"], RDF.type, OWL.ObjectProperty) in g
    chains = list(g.objects(GRAPHRAG["CUSTOMER_CATEGORY"], OWL.propertyChainAxiom))
    assert len(chains) == 1


def test_run_reasoning_ecommerce(ecommerce_erd: ERDSchema):
    """#6: E-commerce 전체 추론."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain="ecommerce")
    assert result.axioms_applied >= 3
    assert result.triples_after >= result.triples_before
    assert "PARENT_OF" in result.transitive_rels


def test_run_reasoning_education():
    """#7: Education 도메인 추론."""
    from pathlib import Path
    ddl_path = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas" / "demo_education.sql"
    if not ddl_path.exists():
        pytest.skip("Education DDL not found")
    from app.ddl_parser.parser import parse_ddl
    erd = parse_ddl(ddl_path.read_text(encoding="utf-8"))
    ontology = build_ontology(erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain="education")
    assert result.axioms_applied >= 2


def test_run_reasoning_no_domain(ecommerce_erd: ERDSchema):
    """#8: 도메인 없이 → axiom 없어서 스킵."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain=None)
    assert result.axioms_applied == 0
    assert result.inferred_count == 0


def test_inference_result_fields(ecommerce_erd: ERDSchema):
    """#9: InferenceResult 필드 검증."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain="ecommerce")
    assert isinstance(result.transitive_rels, list)
    assert isinstance(result.inverse_pairs, list)
    assert isinstance(result.chain_fallback_used, bool)


def test_unknown_axiom_type(ecommerce_erd: ERDSchema):
    """#10 (부정): 알 수 없는 axiom_type → 경고만, 에러 없음."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    count = apply_axioms(g, [AxiomSpec("FOO", "UNKNOWN_TYPE", "BAR")])
    assert count == 0  # 적용 실패했지만 예외 없음


def test_property_chain_invalid_target():
    """#11 (부정): propertyChain target이 list가 아니면 ValueError."""
    from rdflib import Graph
    g = Graph()
    ax = AxiomSpec("FOO", "propertyChain", "NOT_A_LIST")
    with pytest.raises(ValueError, match="must be list"):
        from app.owl.axiom_registry import _apply_one
        _apply_one(g, ax)
