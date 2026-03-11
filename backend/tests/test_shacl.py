"""SHACL 검증 테스트."""

from __future__ import annotations

from rdflib import URIRef
from rdflib.namespace import RDF

from app.models.schemas import ERDSchema, NodeProperty, NodeType, OntologySpec
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import ontology_to_owl
from app.owl.shacl_generator import generate_shapes, SH_NODE_SHAPE, SH_MIN_COUNT
from app.owl.shacl_validator import validate_shacl


def test_shacl_valid_ontology(ecommerce_erd: ERDSchema):
    """#1: 유효한 온톨로지 → SHACL 검증."""
    ontology = build_ontology(ecommerce_erd)
    owl_graph = ontology_to_owl(ontology)
    shapes = generate_shapes(ontology)
    conforms, issues = validate_shacl(owl_graph, shapes)
    assert isinstance(conforms, bool)
    assert isinstance(issues, list)


def test_shacl_shape_count(ecommerce_erd: ERDSchema):
    """#2: NodeType 수 이상의 SHACL shapes 생성."""
    ontology = build_ontology(ecommerce_erd)
    shapes = generate_shapes(ontology)
    shape_count = sum(1 for _ in shapes.subjects(RDF.type, SH_NODE_SHAPE))
    assert shape_count >= len(ontology.node_types)


def test_shacl_key_property_cardinality(ecommerce_erd: ERDSchema):
    """#3: is_key 프로퍼티에 minCount 1 제약."""
    ontology = build_ontology(ecommerce_erd)
    shapes = generate_shapes(ontology)
    min_count_triples = list(shapes.triples((None, SH_MIN_COUNT, None)))
    key_count = sum(1 for nt in ontology.node_types for p in nt.properties if p.is_key)
    assert len(min_count_triples) == key_count


def test_shacl_empty_ontology():
    """#4: 빈 온톨로지 → SHACL 검증 통과."""
    ontology = OntologySpec(node_types=[], relationship_types=[])
    owl_graph = ontology_to_owl(ontology)
    shapes = generate_shapes(ontology)
    conforms, issues = validate_shacl(owl_graph, shapes)
    assert conforms is True
    assert len(issues) == 0


def test_shacl_minimal_ontology():
    """#5: 최소 온톨로지 shapes 생성."""
    ontology = OntologySpec(
        node_types=[
            NodeType(name="Person", source_table="persons", properties=[
                NodeProperty(name="id", source_column="id", type="integer", is_key=True),
                NodeProperty(name="name", source_column="name", type="string"),
            ]),
        ],
        relationship_types=[],
    )
    shapes = generate_shapes(ontology)
    assert len(shapes) > 0
