"""도메인별 OWL axiom 레지스트리.

도메인별 axiom을 OWL Graph에 적용한다.
Phase 1에서 미리 정의하여 Phase 2 시작을 빠르게 한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rdflib import Graph, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from app.config import settings

logger = logging.getLogger(__name__)

GRAPHRAG = Namespace(settings.owl_base_uri)


@dataclass
class AxiomSpec:
    """단일 OWL axiom 정의."""
    subject: str
    axiom_type: str        # "TransitiveProperty" | "inverseOf" | "propertyChain" | "disjointWith"
    target: str | list[str]
    domain: str = ""
    range_cls: str = ""


# ── 도메인별 axiom 정의 ──────────────────────────────────────────

ECOMMERCE_AXIOMS: list[AxiomSpec] = [
    AxiomSpec("PARENT_OF", "TransitiveProperty", "", domain="Category", range_cls="Category"),
    AxiomSpec("PLACED", "inverseOf", "PLACED_BY"),
    AxiomSpec("CONTAINS", "inverseOf", "CONTAINED_IN"),
    AxiomSpec("CUSTOMER_CATEGORY", "propertyChain", ["PLACED", "CONTAINS", "BELONGS_TO"]),
]

EDUCATION_AXIOMS: list[AxiomSpec] = [
    AxiomSpec("REQUIRES", "TransitiveProperty", "", domain="Course", range_cls="Course"),
    AxiomSpec("TEACHES", "inverseOf", "TAUGHT_BY"),
    AxiomSpec("STUDENT_DEPARTMENT", "propertyChain", ["ENROLLED_IN", "OFFERED_BY"]),
]

INSURANCE_AXIOMS: list[AxiomSpec] = [
    AxiomSpec("COVERS", "inverseOf", "COVERED_BY"),
    AxiomSpec("POLICYHOLDER_CLAIM", "propertyChain", ["HOLDS", "HAS_CLAIM"]),
]

_AXIOM_REGISTRY: dict[str, list[AxiomSpec]] = {
    "ecommerce": ECOMMERCE_AXIOMS,
    "education": EDUCATION_AXIOMS,
    "insurance": INSURANCE_AXIOMS,
}


def get_axioms(domain: str | None) -> list[AxiomSpec]:
    """도메인별 axiom 조회. 미등록 도메인은 빈 리스트."""
    if domain is None:
        return []
    return _AXIOM_REGISTRY.get(domain, [])


def apply_axioms(g: Graph, axioms: list[AxiomSpec]) -> int:
    """OWL Graph에 axiom 적용. 적용된 axiom 수 반환."""
    applied = 0
    for ax in axioms:
        try:
            _apply_one(g, ax)
            applied += 1
        except Exception as e:
            logger.warning("Failed to apply axiom %s: %s", ax.subject, e)
    logger.info("Applied %d/%d axioms", applied, len(axioms))
    return applied


def _apply_one(g: Graph, ax: AxiomSpec) -> None:
    """단일 axiom을 Graph에 적용."""
    subj_uri = GRAPHRAG[ax.subject]

    if ax.axiom_type == "TransitiveProperty":
        g.add((subj_uri, RDF.type, OWL.TransitiveProperty))
        if ax.domain:
            g.add((subj_uri, RDFS.domain, GRAPHRAG[ax.domain]))
        if ax.range_cls:
            g.add((subj_uri, RDFS.range, GRAPHRAG[ax.range_cls]))

    elif ax.axiom_type == "inverseOf":
        inv_uri = GRAPHRAG[ax.target]
        g.add((subj_uri, OWL.inverseOf, inv_uri))
        g.add((inv_uri, RDF.type, OWL.ObjectProperty))
        g.add((inv_uri, OWL.inverseOf, subj_uri))

    elif ax.axiom_type == "propertyChain":
        if not isinstance(ax.target, list):
            raise ValueError(f"propertyChain axiom target must be list, got {type(ax.target)}")
        g.add((subj_uri, RDF.type, OWL.ObjectProperty))
        chain_items = [GRAPHRAG[rel] for rel in ax.target]
        chain_list = Collection(g, None, chain_items)
        g.add((subj_uri, OWL.propertyChainAxiom, chain_list.uri))

    elif ax.axiom_type == "disjointWith":
        g.add((GRAPHRAG[ax.subject], OWL.disjointWith, GRAPHRAG[ax.target]))

    else:
        raise ValueError(f"Unknown axiom type: {ax.axiom_type}")
