"""Incremental Neo4j migration engine — applies OntologyDiff to live graph."""

from __future__ import annotations

import logging
from collections import defaultdict

from app.kg_builder.loader import (
    _BATCH_SIZE,
    _create_constraint,
    _create_index,
    _ensure_name,
    _find_key_prop,
    _load_nodes,
    _load_relationships,
)
from app.models.schemas import (
    MigrationProgress,
    OntologyDiff,
    OntologySpec,
    RelationshipType,
)

logger = logging.getLogger(__name__)


def run_incremental_migration(
    diff: OntologyDiff,
    base_ontology: OntologySpec,
    target_ontology: OntologySpec,
    data: dict[str, list[dict]],
    tenant_id: str | None = None,
    progress_callback=None,
) -> dict[str, int]:
    """Apply diff incrementally to Neo4j. Returns stats dict."""
    from app.db.neo4j_client import get_driver
    from app.tenant import prefixed_label

    driver = get_driver()
    stats = {
        "nodes_added": 0, "nodes_removed": 0,
        "relationships_added": 0, "relationships_removed": 0,
        "properties_modified": 0,
    }

    target_node_map = {nt.name: nt for nt in target_ontology.node_types}
    target_rel_map = {rt.name: rt for rt in target_ontology.relationship_types}
    node_key_map = {nt.name: _find_key_prop(nt) for nt in target_ontology.node_types}
    # Also include base keys for removal operations
    for nt in base_ontology.node_types:
        if nt.name not in node_key_map:
            node_key_map[nt.name] = _find_key_prop(nt)

    def _update_progress(step: str, step_num: int):
        if progress_callback:
            progress_callback(MigrationProgress(
                current_step=step, step_number=step_num, total_steps=6,
                **stats,
            ))

    with driver.session() as session:
        # ── Phase 1: Remove relationships ────────────────────────
        _update_progress("remove_relationships", 1)
        for rd in diff.relationship_diffs:
            if rd.change_type == "removed" or rd.endpoint_changed:
                count = session.run(
                    f"MATCH ()-[r:`{rd.name}`]->() DELETE r RETURN count(r) AS c"
                ).single()
                removed = count["c"] if count else 0
                stats["relationships_removed"] += removed
                logger.info("Removed %d '%s' relationships", removed, rd.name)

        # ── Phase 2: Remove nodes ────────────────────────────────
        _update_progress("remove_nodes", 2)
        for nd in diff.node_diffs:
            if nd.change_type == "removed":
                lbl = prefixed_label(tenant_id, nd.name)
                count = session.run(
                    f"MATCH (n:`{lbl}`) DETACH DELETE n RETURN count(n) AS c"
                ).single()
                removed = count["c"] if count else 0
                stats["nodes_removed"] += removed
                # Drop constraint
                key_prop = node_key_map.get(nd.name, "id")
                try:
                    session.run(
                        f"DROP CONSTRAINT IF EXISTS "
                        f"FOR (n:`{lbl}`) REQUIRE n.`{key_prop}` IS UNIQUE"
                    )
                except Exception:
                    pass
                logger.info("Removed %d '%s' nodes", removed, nd.name)

        # ── Phase 3: Modify existing node properties ─────────────
        _update_progress("modify_properties", 3)
        for nd in diff.node_diffs:
            if nd.change_type != "modified":
                continue
            lbl = prefixed_label(tenant_id, nd.name)
            for pc in nd.property_changes:
                if pc.name.startswith("_"):
                    continue  # skip meta changes
                if pc.change_type == "removed":
                    session.run(f"MATCH (n:`{lbl}`) REMOVE n.`{pc.name}`")
                    stats["properties_modified"] += 1
                elif pc.change_type == "added":
                    # Set default null for new properties
                    session.run(f"MATCH (n:`{lbl}`) SET n.`{pc.name}` = null")
                    stats["properties_modified"] += 1

        # ── Phase 4: Add new nodes ───────────────────────────────
        _update_progress("add_nodes", 4)
        for nd in diff.node_diffs:
            if nd.change_type != "added":
                continue
            nt = target_node_map.get(nd.name)
            if not nt:
                continue
            lbl = prefixed_label(tenant_id, nt.name)
            key_prop = _find_key_prop(nt)
            prop_names = [p.name for p in nt.properties]

            # Create constraint first
            session.execute_write(_create_constraint, lbl, key_prop)
            for prop in nt.properties:
                if prop.name != key_prop:
                    session.execute_write(_create_index, lbl, prop.name)

            rows = data.get(nt.source_table, [])
            rows = _ensure_name(nt.name, rows, prop_names)
            if "name" not in prop_names:
                prop_names.append("name")

            if rows:
                for i in range(0, len(rows), _BATCH_SIZE):
                    batch = rows[i: i + _BATCH_SIZE]
                    session.execute_write(_load_nodes, lbl, key_prop, prop_names, batch)
                stats["nodes_added"] += len(rows)
                logger.info("Added %d '%s' nodes", len(rows), nd.name)

        # ── Phase 5: Add new relationships ───────────────────────
        _update_progress("add_relationships", 5)
        rels_to_add = []
        for rd in diff.relationship_diffs:
            if rd.change_type == "added" or rd.endpoint_changed:
                rt = target_rel_map.get(rd.name)
                if rt:
                    rels_to_add.append(rt)

        for rel in rels_to_add:
            src_key = node_key_map.get(rel.source_node, "id")
            tgt_key = node_key_map.get(rel.target_node, "id")
            table_rows = data.get(rel.data_table, [])
            loader_rows: list[dict] = []
            for row in table_rows:
                src_val = row.get(rel.source_key_column)
                tgt_val = row.get(rel.target_key_column)
                if src_val is None or tgt_val is None:
                    continue
                lr = {"__src": src_val, "__tgt": tgt_val}
                for p in rel.properties:
                    lr[p.source_column] = row.get(p.source_column)
                loader_rows.append(lr)

            if loader_rows:
                prefixed_rel = RelationshipType(
                    name=rel.name,
                    source_node=prefixed_label(tenant_id, rel.source_node),
                    target_node=prefixed_label(tenant_id, rel.target_node),
                    data_table=rel.data_table,
                    source_key_column=rel.source_key_column,
                    target_key_column=rel.target_key_column,
                    properties=rel.properties,
                    derivation=rel.derivation,
                )
                for i in range(0, len(loader_rows), _BATCH_SIZE):
                    batch = loader_rows[i: i + _BATCH_SIZE]
                    session.execute_write(
                        _load_relationships, prefixed_rel, batch, src_key, tgt_key
                    )
                stats["relationships_added"] += len(loader_rows)
                logger.info("Added %d '%s' relationships", len(loader_rows), rel.name)

        # ── Phase 6: Update constraints for modified nodes ───────
        _update_progress("update_constraints", 6)
        for nd in diff.node_diffs:
            if nd.change_type == "modified":
                nt = target_node_map.get(nd.name)
                if nt:
                    lbl = prefixed_label(tenant_id, nt.name)
                    key_prop = _find_key_prop(nt)
                    session.execute_write(_create_constraint, lbl, key_prop)

    return stats
