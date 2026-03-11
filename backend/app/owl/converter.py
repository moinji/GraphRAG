"""OntologySpec ↔ rdflib OWL Graph 양방향 변환.

OntologySpec의 NodeType → owl:Class, RelationshipType → owl:ObjectProperty,
NodeProperty → owl:DatatypeProperty로 매핑한다.
"""

from __future__ import annotations

import logging

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from app.config import settings
from app.models.schemas import (
    NodeProperty,
    NodeType,
    OntologySpec,
    RelationshipType,
    RelProperty,
)

logger = logging.getLogger(__name__)

GRAPHRAG = Namespace(settings.owl_base_uri)

_XSD_MAP: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "float": XSD.decimal,
    "boolean": XSD.boolean,
}


def local_name(uri) -> str:
    """URI에서 로컬 이름 추출. ex) http://graphrag.io/ontology#Customer → Customer

    Public API — reasoner.py, schema_enricher.py에서도 사용.
    """
    if uri is None:
        return ""
    s = str(uri)
    return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]


def ontology_to_owl(
    ontology: OntologySpec,
    domain: str | None = None,
) -> Graph:
    """OntologySpec → rdflib OWL Graph 변환.

    Args:
        ontology: 변환할 온톨로지
        domain: 도메인 이름 (메타데이터용)

    Returns:
        OWL axiom이 포함된 rdflib Graph
    """
    g = Graph()
    g.bind("gr", GRAPHRAG)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)

    # 온톨로지 메타데이터
    onto_uri = GRAPHRAG["Ontology"]
    g.add((onto_uri, RDF.type, OWL.Ontology))
    if domain:
        g.add((onto_uri, RDFS.comment, Literal(f"Domain: {domain}")))

    # NodeType → owl:Class + DatatypeProperty
    for nt in ontology.node_types:
        cls_uri = GRAPHRAG[nt.name]
        g.add((cls_uri, RDF.type, OWL.Class))
        g.add((cls_uri, RDFS.label, Literal(nt.name)))
        g.add((cls_uri, GRAPHRAG.sourceTable, Literal(nt.source_table)))

        for prop in nt.properties:
            prop_uri = GRAPHRAG[f"{nt.name}.{prop.name}"]
            g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
            g.add((prop_uri, RDFS.label, Literal(prop.name)))
            g.add((prop_uri, RDFS.domain, cls_uri))
            g.add((prop_uri, RDFS.range, _XSD_MAP.get(prop.type, XSD.string)))
            g.add((prop_uri, GRAPHRAG.sourceColumn, Literal(prop.source_column)))
            if prop.is_key:
                g.add((prop_uri, RDF.type, OWL.FunctionalProperty))

    # RelationshipType → owl:ObjectProperty
    for rel in ontology.relationship_types:
        rel_uri = GRAPHRAG[rel.name]
        g.add((rel_uri, RDF.type, OWL.ObjectProperty))
        g.add((rel_uri, RDFS.label, Literal(rel.name)))
        g.add((rel_uri, RDFS.domain, GRAPHRAG[rel.source_node]))
        g.add((rel_uri, RDFS.range, GRAPHRAG[rel.target_node]))
        g.add((rel_uri, GRAPHRAG.derivation, Literal(rel.derivation)))
        g.add((rel_uri, GRAPHRAG.dataTable, Literal(rel.data_table)))
        g.add((rel_uri, GRAPHRAG.sourceKeyColumn, Literal(rel.source_key_column)))
        g.add((rel_uri, GRAPHRAG.targetKeyColumn, Literal(rel.target_key_column)))

        for rp in rel.properties:
            rp_uri = GRAPHRAG[f"{rel.name}.{rp.name}"]
            g.add((rp_uri, RDF.type, OWL.DatatypeProperty))
            g.add((rp_uri, RDFS.domain, rel_uri))
            g.add((rp_uri, RDFS.range, _XSD_MAP.get(rp.type, XSD.string)))

    logger.info(
        "OntologySpec → OWL: %d classes, %d object properties, %d total triples",
        len(ontology.node_types),
        len(ontology.relationship_types),
        len(g),
    )
    return g


def owl_to_ontology(g: Graph) -> OntologySpec:
    """rdflib OWL Graph → OntologySpec 역변환 (round-trip 보장)."""
    node_types: list[NodeType] = []
    relationship_types: list[RelationshipType] = []

    # owl:Class → NodeType
    for cls_uri in g.subjects(RDF.type, OWL.Class):
        if isinstance(cls_uri, BNode):
            continue
        name = local_name(cls_uri)
        source_table = str(g.value(cls_uri, GRAPHRAG.sourceTable) or name.lower())

        props: list[NodeProperty] = []
        for dp_uri in g.subjects(RDFS.domain, cls_uri):
            if (dp_uri, RDF.type, OWL.DatatypeProperty) not in g:
                continue
            dp_name = str(g.value(dp_uri, RDFS.label) or local_name(dp_uri))
            if "." in dp_name:
                dp_name = dp_name.split(".", 1)[1]
            source_col = str(g.value(dp_uri, GRAPHRAG.sourceColumn) or dp_name)
            range_uri = g.value(dp_uri, RDFS.range)
            prop_type = _reverse_xsd(range_uri) if range_uri else "string"
            is_key = (dp_uri, RDF.type, OWL.FunctionalProperty) in g
            props.append(NodeProperty(
                name=dp_name, source_column=source_col, type=prop_type, is_key=is_key,
            ))

        node_types.append(NodeType(name=name, source_table=source_table, properties=props))

    # owl:ObjectProperty → RelationshipType
    for rel_uri in g.subjects(RDF.type, OWL.ObjectProperty):
        if isinstance(rel_uri, BNode):
            continue
        name = local_name(rel_uri)
        source_node = local_name(g.value(rel_uri, RDFS.domain)) if g.value(rel_uri, RDFS.domain) else ""
        target_node = local_name(g.value(rel_uri, RDFS.range)) if g.value(rel_uri, RDFS.range) else ""
        derivation = str(g.value(rel_uri, GRAPHRAG.derivation) or "fk_direct")
        data_table = str(g.value(rel_uri, GRAPHRAG.dataTable) or "")
        source_key = str(g.value(rel_uri, GRAPHRAG.sourceKeyColumn) or "id")
        target_key = str(g.value(rel_uri, GRAPHRAG.targetKeyColumn) or "id")

        rel_props: list[RelProperty] = []
        for rp_uri in g.subjects(RDFS.domain, rel_uri):
            if (rp_uri, RDF.type, OWL.DatatypeProperty) not in g:
                continue
            rp_local = local_name(rp_uri)
            rp_name = rp_local.split(".", 1)[1] if "." in rp_local else rp_local
            rp_range = g.value(rp_uri, RDFS.range)
            rp_type = _reverse_xsd(rp_range) if rp_range else "string"
            rp_source = rp_name
            rel_props.append(RelProperty(name=rp_name, source_column=rp_source, type=rp_type))

        relationship_types.append(RelationshipType(
            name=name, source_node=source_node, target_node=target_node,
            data_table=data_table, source_key_column=source_key,
            target_key_column=target_key, properties=rel_props,
            derivation=derivation,
        ))

    return OntologySpec(node_types=node_types, relationship_types=relationship_types)


def serialize_owl(g: Graph, fmt: str = "turtle") -> str:
    """OWL Graph를 문자열로 직렬화."""
    return g.serialize(format=fmt)


def _reverse_xsd(uri: URIRef | None) -> str:
    """XSD URI → 프로퍼티 타입 문자열."""
    if uri is None:
        return "string"
    rev = {v: k for k, v in _XSD_MAP.items()}
    return rev.get(uri, "string")
