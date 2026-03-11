"""graph_schema에 OWL 메타데이터(계층, 전이적, 체인) 병합.

get_graph_schema()에서 enable_owl=True일 때 호출되어
스키마 dict에 OWL 정보를 추가한다.
"""

from __future__ import annotations

import logging

from rdflib import Graph
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from app.owl.converter import local_name

logger = logging.getLogger(__name__)


def enrich_schema_with_owl(
    neo4j_schema: dict,
    owl_graph: Graph,
) -> dict:
    """Neo4j 스키마에 OWL 메타데이터 병합.

    추가되는 키:
    - class_hierarchy: {cls: [parent_cls, ...]}
    - transitive_properties: [rel_name, ...]
    - inverse_pairs: [(rel1, rel2), ...]
    - inferred_paths: [[rel1, rel2, ...], ...]
    """
    enriched = dict(neo4j_schema)

    # 1. 클래스 계층
    hierarchy: dict[str, list[str]] = {}
    for cls in owl_graph.subjects(RDF.type, OWL.Class):
        parents = [
            local_name(p)
            for p in owl_graph.objects(cls, RDFS.subClassOf)
            if local_name(p)
        ]
        if parents:
            hierarchy[local_name(cls)] = parents
    enriched["class_hierarchy"] = hierarchy

    # 2. 전이적 관계
    enriched["transitive_properties"] = [
        local_name(p)
        for p in owl_graph.subjects(RDF.type, OWL.TransitiveProperty)
        if local_name(p)
    ]

    # 3. 역관계 쌍
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for s, _, o in owl_graph.triples((None, OWL.inverseOf, None)):
        pair = (min(local_name(s), local_name(o)), max(local_name(s), local_name(o)))
        if pair not in seen and pair[0] and pair[1]:
            seen.add(pair)
            pairs.append(pair)
    enriched["inverse_pairs"] = pairs

    # 4. 프로퍼티 체인
    chains: list[list[str]] = []
    for prop in owl_graph.subjects(OWL.propertyChainAxiom, None):
        chain_node = owl_graph.value(prop, OWL.propertyChainAxiom)
        if chain_node is not None:
            try:
                chain = [local_name(item) for item in Collection(owl_graph, chain_node)]
                if chain:
                    chains.append(chain)
            except Exception:
                pass
    enriched["inferred_paths"] = chains

    return enriched
