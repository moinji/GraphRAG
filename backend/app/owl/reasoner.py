"""OWL-RL 추론 실행 + 추론 결과 추출.

rdflib 인메모리 Graph에서 OWL-RL 추론을 실행하고,
새로 추론된 트리플을 추출한다.
propertyChain 미지원 시 fallback 전략 포함.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from rdflib import Graph
from rdflib.namespace import OWL, RDF, RDFS

from app.config import settings
from app.owl.axiom_registry import AxiomSpec, apply_axioms, get_axioms
from app.owl.converter import GRAPHRAG, local_name

logger = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    """추론 결과."""
    axioms_applied: int
    triples_before: int
    triples_after: int
    inferred_count: int
    transitive_rels: list[str]
    inverse_pairs: list[tuple[str, str]]
    chain_fallback_used: bool = False


def _run_owlrl_with_timeout(g: Graph, timeout_sec: int) -> bool:
    """OWL-RL 추론을 Windows-safe timeout으로 실행. 성공 시 True."""
    success = [False]
    exc_holder = [None]

    def _target():
        try:
            from owlrl import DeductiveClosure, OWLRL_Semantics
            DeductiveClosure(OWLRL_Semantics).expand(g)
            success[0] = True
        except Exception as e:
            exc_holder[0] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)

    if t.is_alive():
        logger.warning("OWL-RL reasoning exceeded %ds timeout", timeout_sec)
        return False
    if exc_holder[0]:
        logger.warning("OWL-RL reasoning failed: %s", exc_holder[0])
        return False
    return success[0]


def run_reasoning(
    owl_graph: Graph,
    domain: str | None = None,
    extra_axioms: list[AxiomSpec] | None = None,
) -> InferenceResult:
    """OWL-RL 추론 실행.

    Args:
        owl_graph: axiom이 적용될 OWL Graph (in-place 수정)
        domain: 도메인명 (axiom 레지스트리 조회용)
        extra_axioms: 추가 axiom

    Returns:
        InferenceResult — 추론 통계
    """
    axioms = get_axioms(domain)
    if extra_axioms:
        axioms = axioms + extra_axioms

    if not axioms:
        logger.info("No axioms to apply — skipping reasoning")
        return InferenceResult(0, len(owl_graph), len(owl_graph), 0, [], [])

    before_count = len(owl_graph)

    # 1. axiom 적용
    applied = apply_axioms(owl_graph, axioms)

    # 2. OWL-RL 추론 (Windows-safe timeout)
    chain_fallback = False
    try:
        reasoning_ok = _run_owlrl_with_timeout(
            owl_graph, settings.owl_reasoning_timeout_sec,
        )
        if not reasoning_ok:
            logger.warning("OWL-RL reasoning skipped — axioms applied but no inference")
    except Exception as e:
        logger.warning("OWL-RL import or reasoning failed: %s", e)

    after_count = len(owl_graph)
    inferred = after_count - before_count

    # 추론 상한 체크
    if inferred > settings.owl_max_inferred_triples:
        logger.warning(
            "Inferred %d triples exceeds limit %d",
            inferred, settings.owl_max_inferred_triples,
        )

    # 3. propertyChain fallback 검사
    chain_axioms = [a for a in axioms if a.axiom_type == "propertyChain"]
    if chain_axioms:
        for ca in chain_axioms:
            # 체인에 의해 생성된 트리플이 있는지 확인
            subj_uri = GRAPHRAG[ca.subject]
            chain_triples = list(owl_graph.triples((None, subj_uri, None)))
            if not chain_triples:
                chain_fallback = True
                logger.info("propertyChain %s produced no inferences — fallback needed", ca.subject)

    # 4. 메타데이터 추출
    transitive_rels = [
        local_name(s)
        for s in owl_graph.subjects(RDF.type, OWL.TransitiveProperty)
    ]
    inverse_pairs = []
    for s, _, o in owl_graph.triples((None, OWL.inverseOf, None)):
        s_name = local_name(s)
        o_name = local_name(o)
        if s_name and o_name and (o_name, s_name) not in inverse_pairs:
            inverse_pairs.append((s_name, o_name))

    logger.info(
        "Reasoning complete: %d axioms, %d→%d triples (+%d inferred), "
        "%d transitive, %d inverse pairs, chain_fallback=%s",
        applied, before_count, after_count, inferred,
        len(transitive_rels), len(inverse_pairs), chain_fallback,
    )

    return InferenceResult(
        axioms_applied=applied,
        triples_before=before_count,
        triples_after=after_count,
        inferred_count=inferred,
        transitive_rels=transitive_rels,
        inverse_pairs=inverse_pairs,
        chain_fallback_used=chain_fallback,
    )
