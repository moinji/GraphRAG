"""Impact analysis — query live Neo4j to assess migration scope."""

from __future__ import annotations

import logging

from app.models.schemas import ImpactAnalysis, OntologyDiff, OntologySpec

logger = logging.getLogger(__name__)


def analyze_impact(
    diff: OntologyDiff,
    base_ontology: OntologySpec,
    target_ontology: OntologySpec,
    tenant_id: str | None = None,
) -> ImpactAnalysis:
    """Query Neo4j for counts of affected nodes/relationships."""
    from app.db.neo4j_client import get_driver
    from app.tenant import prefixed_label

    driver = get_driver()
    node_counts: dict[str, int] = {}
    rel_counts: dict[str, int] = {}
    warnings: list[str] = []

    target_node_names = {nt.name for nt in target_ontology.node_types}

    with driver.session() as session:
        # Count nodes for removed/modified node types
        for nd in diff.node_diffs:
            if nd.change_type in ("removed", "modified"):
                lbl = prefixed_label(tenant_id, nd.name)
                count = session.run(
                    f"MATCH (n:`{lbl}`) RETURN count(n) AS c"
                ).single()["c"]
                if count > 0:
                    node_counts[nd.name] = count

        # Count relationships for removed/modified types
        for rd in diff.relationship_diffs:
            if rd.change_type in ("removed", "modified"):
                count = session.run(
                    f"MATCH ()-[r:`{rd.name}`]->() RETURN count(r) AS c"
                ).single()["c"]
                if count > 0:
                    rel_counts[rd.name] = count

    # Orphan detection: removed nodes referenced by remaining relationships
    base_rel_map = {rt.name: rt for rt in base_ontology.relationship_types}
    for nd in diff.node_diffs:
        if nd.change_type == "removed":
            for rt in target_ontology.relationship_types:
                if rt.source_node == nd.name or rt.target_node == nd.name:
                    warnings.append(
                        f"Removing node '{nd.name}' but relationship "
                        f"'{rt.name}' still references it"
                    )

    # Broken endpoint warning
    for rd in diff.relationship_diffs:
        if rd.change_type in ("added", "modified"):
            if rd.source_node not in target_node_names:
                warnings.append(
                    f"Relationship '{rd.name}' references missing source node '{rd.source_node}'"
                )
            if rd.target_node not in target_node_names:
                warnings.append(
                    f"Relationship '{rd.name}' references missing target node '{rd.target_node}'"
                )

    total_nodes = sum(node_counts.values())
    total_rels = sum(rel_counts.values())
    # Heuristic: ~1ms per node, ~2ms per relationship
    estimated = (total_nodes * 0.001) + (total_rels * 0.002)

    return ImpactAnalysis(
        affected_node_counts=node_counts,
        affected_relationship_counts=rel_counts,
        total_affected_nodes=total_nodes,
        total_affected_relationships=total_rels,
        warnings=warnings,
        estimated_duration_seconds=round(estimated, 2),
    )
