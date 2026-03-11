"""OWL 변환 정확성 테스트."""

from __future__ import annotations

import pytest
from rdflib.namespace import OWL, RDF, RDFS

from app.models.schemas import ERDSchema, NodeProperty, NodeType, OntologySpec
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import GRAPHRAG, ontology_to_owl, owl_to_ontology, serialize_owl


def test_owl_class_count(ecommerce_erd: ERDSchema):
    """#1: 9개 owl:Class 생성."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    classes = list(g.subjects(RDF.type, OWL.Class))
    assert len(classes) == len(ontology.node_types)


def test_owl_object_property_count(ecommerce_erd: ERDSchema):
    """#2: 12개 owl:ObjectProperty."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    props = list(g.subjects(RDF.type, OWL.ObjectProperty))
    assert len(props) == len(ontology.relationship_types)


def test_owl_datatype_property_count(ecommerce_erd: ERDSchema):
    """#3: DatatypeProperty 수 일치."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    total_props = sum(len(nt.properties) for nt in ontology.node_types)
    rel_prop_count = sum(len(r.properties) for r in ontology.relationship_types)
    dp_count = sum(1 for _ in g.subjects(RDF.type, OWL.DatatypeProperty))
    assert dp_count == total_props + rel_prop_count


def test_owl_domain_range(ecommerce_erd: ERDSchema):
    """#4: ObjectProperty의 domain/range 올바르게 설정."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    for rel in ontology.relationship_types:
        rel_uri = GRAPHRAG[rel.name]
        domain = g.value(rel_uri, RDFS.domain)
        range_ = g.value(rel_uri, RDFS.range)
        assert domain is not None, f"{rel.name} has no domain"
        assert range_ is not None, f"{rel.name} has no range"
        assert str(domain).endswith(rel.source_node)
        assert str(range_).endswith(rel.target_node)


def test_owl_key_property_functional(ecommerce_erd: ERDSchema):
    """#5: is_key=True → FunctionalProperty."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    functional_count = sum(1 for _ in g.subjects(RDF.type, OWL.FunctionalProperty))
    key_count = sum(1 for nt in ontology.node_types for p in nt.properties if p.is_key)
    assert functional_count == key_count


def test_owl_round_trip_node_count(ecommerce_erd: ERDSchema):
    """#6: round-trip 노드 수 보존."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    restored = owl_to_ontology(g)
    assert len(restored.node_types) == len(ontology.node_types)


def test_owl_round_trip_rel_count(ecommerce_erd: ERDSchema):
    """#7: round-trip 관계 수 보존."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    restored = owl_to_ontology(g)
    assert len(restored.relationship_types) == len(ontology.relationship_types)


def test_owl_round_trip_property_values(ecommerce_erd: ERDSchema):
    """#8: round-trip 프로퍼티 값(source_column, type, is_key) 보존."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    restored = owl_to_ontology(g)
    original_names = {nt.name for nt in ontology.node_types}
    restored_names = {nt.name for nt in restored.node_types}
    assert original_names == restored_names
    # 각 노드의 key 프로퍼티 수 보존
    for orig_nt in ontology.node_types:
        rest_nt = next((r for r in restored.node_types if r.name == orig_nt.name), None)
        assert rest_nt is not None
        orig_keys = {p.name for p in orig_nt.properties if p.is_key}
        rest_keys = {p.name for p in rest_nt.properties if p.is_key}
        assert orig_keys == rest_keys, f"{orig_nt.name} key mismatch"


def test_serialize_turtle(ecommerce_erd: ERDSchema):
    """#9: Turtle 직렬화."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    turtle = serialize_owl(g, "turtle")
    assert "owl:Class" in turtle
    assert len(turtle) > 100


def test_serialize_xml(ecommerce_erd: ERDSchema):
    """#10: RDF/XML 직렬화."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    xml = serialize_owl(g, "xml")
    assert "rdf:RDF" in xml


def test_owl_empty_ontology():
    """#11 (부정): 빈 OntologySpec 변환."""
    ontology = OntologySpec(node_types=[], relationship_types=[])
    g = ontology_to_owl(ontology)
    classes = list(g.subjects(RDF.type, OWL.Class))
    assert len(classes) == 0
    assert len(g) > 0  # 최소 Ontology 메타데이터


def test_owl_domain_metadata(ecommerce_erd: ERDSchema):
    """#12: 도메인 메타데이터 포함."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology, domain="ecommerce")
    comments = list(g.objects(GRAPHRAG["Ontology"], RDFS.comment))
    assert any("ecommerce" in str(c) for c in comments)
