"""OntologySpec → SHACL Shapes Graph 자동 생성.

TBox-level schema consistency shapes를 생성한다.
인스턴스(ABox) 검증이 아닌 온톨로지 구조 검증용이다.
"""

from __future__ import annotations

import logging

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from app.config import settings
from app.models.schemas import OntologySpec

logger = logging.getLogger(__name__)

# 명시적 URIRef로 SHACL 프로퍼티 정의 — Python 예약어 충돌 방지
SH_NS = "http://www.w3.org/ns/shacl#"
SH_NODE_SHAPE = URIRef(f"{SH_NS}NodeShape")
SH_TARGET_CLASS = URIRef(f"{SH_NS}targetClass")
SH_PROPERTY = URIRef(f"{SH_NS}property")
SH_PATH = URIRef(f"{SH_NS}path")
SH_DATATYPE = URIRef(f"{SH_NS}datatype")
SH_MIN_COUNT = URIRef(f"{SH_NS}minCount")
SH_MAX_COUNT = URIRef(f"{SH_NS}maxCount")
SH_CLASS = URIRef(f"{SH_NS}class")

GRAPHRAG_NS = settings.owl_base_uri
GRAPHRAG = lambda name: URIRef(f"{GRAPHRAG_NS}{name}")  # noqa: E731

_XSD_MAP: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "float": XSD.decimal,
    "boolean": XSD.boolean,
}


def generate_shapes(ontology: OntologySpec) -> Graph:
    """OntologySpec에서 SHACL shapes Graph 생성.

    TBox-level schema consistency check용 shapes:
    - 각 NodeType → NodeShape (targetClass)
    - 각 프로퍼티 → PropertyShape (datatype 제약)
    - key 프로퍼티 → minCount 1 / maxCount 1
    - 각 RelationshipType → domain/range 검증 shape
    """
    g = Graph()
    g.bind("sh", SH_NS)
    g.bind("gr", GRAPHRAG_NS)
    g.bind("xsd", str(XSD))

    for nt in ontology.node_types:
        shape_uri = GRAPHRAG(f"{nt.name}Shape")
        cls_uri = GRAPHRAG(nt.name)

        g.add((shape_uri, RDF.type, SH_NODE_SHAPE))
        g.add((shape_uri, SH_TARGET_CLASS, cls_uri))

        for prop in nt.properties:
            prop_shape = GRAPHRAG(f"{nt.name}_{prop.name}_Shape")
            g.add((shape_uri, SH_PROPERTY, prop_shape))
            g.add((prop_shape, SH_PATH, GRAPHRAG(f"{nt.name}.{prop.name}")))
            g.add((prop_shape, SH_DATATYPE, _XSD_MAP.get(prop.type, XSD.string)))

            if prop.is_key:
                g.add((prop_shape, SH_MIN_COUNT, Literal(1)))
                g.add((prop_shape, SH_MAX_COUNT, Literal(1)))

    # RelationshipType → domain/range 검증 shape
    node_names = {nt.name for nt in ontology.node_types}
    for rel in ontology.relationship_types:
        if rel.source_node not in node_names or rel.target_node not in node_names:
            continue

        rel_shape = GRAPHRAG(f"{rel.name}_RelShape")
        g.add((rel_shape, RDF.type, SH_NODE_SHAPE))
        g.add((rel_shape, SH_TARGET_CLASS, GRAPHRAG(rel.source_node)))

        prop_shape = GRAPHRAG(f"{rel.name}_target_Shape")
        g.add((rel_shape, SH_PROPERTY, prop_shape))
        g.add((prop_shape, SH_PATH, GRAPHRAG(rel.name)))
        g.add((prop_shape, SH_CLASS, GRAPHRAG(rel.target_node)))

    shape_count = sum(1 for _ in g.subjects(RDF.type, SH_NODE_SHAPE))
    logger.info("Generated %d SHACL shapes (%d total triples)", shape_count, len(g))
    return g
