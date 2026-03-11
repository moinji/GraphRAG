"""OWL 추론 결과를 Neo4j에 물리화.

전이적 클로저 관계 + propertyChain fallback을 Neo4j에 MERGE.
"""

from __future__ import annotations

import logging

from app.models.schemas import OntologySpec
from app.owl.axiom_registry import AxiomSpec, get_axioms

logger = logging.getLogger(__name__)


def materialize_transitive(
    ontology: OntologySpec,
    driver,
    tenant_id: str | None = None,
) -> dict[str, int]:
    """자기 참조 관계(전이적 후보)의 클로저를 Neo4j에 물리화."""
    from app.tenant import tenant_label_prefix
    prefix = tenant_label_prefix(tenant_id)

    transitive_rels = [
        rel for rel in ontology.relationship_types
        if rel.source_node == rel.target_node
    ]

    results: dict[str, int] = {}
    for rel in transitive_rels:
        label = f"{prefix}{rel.source_node}" if prefix else rel.source_node
        closure_name = f"{rel.name}_CLOSURE"

        cypher = (
            f"MATCH (a:`{label}`)-[:`{rel.name}`*2..5]->(b:`{label}`) "
            f"WHERE a <> b AND NOT (a)-[:`{closure_name}`]->(b) "
            f"MERGE (a)-[r:`{closure_name}`]->(b) "
            f"SET r.inferred = true, r.derivation = 'owl_transitive' "
            f"RETURN count(r) AS created"
        )

        try:
            with driver.session() as session:
                result = session.run(cypher)
                created = result.single()["created"]
                results[rel.name] = created
                if created > 0:
                    logger.info("Materialized %d closure edges for %s", created, rel.name)
        except Exception as e:
            logger.warning("Failed to materialize %s: %s", rel.name, e)
            results[rel.name] = 0

    total = sum(results.values())
    logger.info("Materialization complete: %d total closure edges", total)
    return results


def materialize_chain_fallback(
    driver,
    chain_axioms: list[AxiomSpec],
    tenant_id: str | None = None,
) -> dict[str, int]:
    """owlrl이 propertyChain을 처리하지 못한 경우, Cypher로 직접 물리화."""
    from app.tenant import tenant_label_prefix
    prefix = tenant_label_prefix(tenant_id)

    results: dict[str, int] = {}
    for ax in chain_axioms:
        if not isinstance(ax.target, list) or len(ax.target) < 2:
            continue

        # 체인 경로 패턴 생성: (a)-[:R1]->()-[:R2]->...->(b)
        path_parts = []
        for i, rel in enumerate(ax.target):
            if i == 0:
                path_parts.append(f"(a)-[:`{rel}`]->()")
            elif i == len(ax.target) - 1:
                path_parts.append(f"-[:`{rel}`]->(b)")
            else:
                path_parts.append(f"-[:`{rel}`]->()")

        match_pattern = "".join(path_parts)
        chain_name = ax.subject

        cypher = (
            f"MATCH {match_pattern} "
            f"WHERE a <> b "
            f"MERGE (a)-[r:`{chain_name}`]->(b) "
            f"SET r.inferred = true, r.derivation = 'owl_chain_fallback' "
            f"RETURN count(r) AS created"
        )

        try:
            with driver.session() as session:
                result = session.run(cypher)
                created = result.single()["created"]
                results[chain_name] = created
                if created > 0:
                    logger.info("Chain fallback: %d edges for %s", created, chain_name)
        except Exception as e:
            logger.warning("Chain fallback failed for %s: %s", chain_name, e)
            results[chain_name] = 0

    return results


def cleanup_inferred(driver, tenant_id: str | None = None) -> int:
    """물리화된 추론 관계 삭제 (KG 리빌드 전 정리용)."""
    cypher = "MATCH ()-[r]->() WHERE r.inferred = true DELETE r RETURN count(r) AS deleted"
    try:
        with driver.session() as session:
            result = session.run(cypher)
            deleted = result.single()["deleted"]
            logger.info("Cleaned up %d inferred relationships", deleted)
            return deleted
    except Exception as e:
        logger.warning("Failed to cleanup inferred relationships: %s", e)
        return 0
