"""Pure ontology diff engine — no I/O, deterministic."""

from __future__ import annotations

from app.models.schemas import (
    NodeType,
    NodeTypeDiff,
    OntologyDiff,
    OntologySpec,
    PropertyChange,
    RelationshipType,
    RelationshipTypeDiff,
)


def compute_diff(
    base: OntologySpec,
    target: OntologySpec,
    base_version_id: int = 0,
    target_version_id: int = 0,
) -> OntologyDiff:
    """Compare two OntologySpec instances and return a structured diff."""
    node_diffs = _diff_nodes(base.node_types, target.node_types)
    rel_diffs = _diff_relationships(base.relationship_types, target.relationship_types)

    is_breaking = any(
        d.change_type == "removed" for d in node_diffs
    ) or any(
        d.change_type == "removed" or d.endpoint_changed for d in rel_diffs
    )

    summary = _build_summary(node_diffs, rel_diffs)

    return OntologyDiff(
        base_version_id=base_version_id,
        target_version_id=target_version_id,
        node_diffs=node_diffs,
        relationship_diffs=rel_diffs,
        summary=summary,
        is_breaking=is_breaking,
    )


def _diff_nodes(base: list[NodeType], target: list[NodeType]) -> list[NodeTypeDiff]:
    base_map = {nt.name: nt for nt in base}
    target_map = {nt.name: nt for nt in target}
    diffs: list[NodeTypeDiff] = []

    # Added
    for name in target_map:
        if name not in base_map:
            diffs.append(NodeTypeDiff(
                name=name,
                change_type="added",
                source_table=target_map[name].source_table,
            ))

    # Removed
    for name in base_map:
        if name not in target_map:
            diffs.append(NodeTypeDiff(
                name=name,
                change_type="removed",
                source_table=base_map[name].source_table,
            ))

    # Modified
    for name in base_map:
        if name in target_map:
            b = base_map[name]
            t = target_map[name]
            prop_changes = _diff_node_properties(b, t)
            table_changed = b.source_table != t.source_table
            if prop_changes or table_changed:
                changes = list(prop_changes)
                if table_changed:
                    changes.append(PropertyChange(
                        name="_source_table",
                        change_type="modified",
                        old_value=b.source_table,
                        new_value=t.source_table,
                    ))
                diffs.append(NodeTypeDiff(
                    name=name,
                    change_type="modified",
                    source_table=t.source_table,
                    property_changes=changes,
                ))

    return diffs


def _diff_node_properties(base: NodeType, target: NodeType) -> list[PropertyChange]:
    base_props = {p.name: p for p in base.properties}
    target_props = {p.name: p for p in target.properties}
    changes: list[PropertyChange] = []

    for name in target_props:
        if name not in base_props:
            changes.append(PropertyChange(name=name, change_type="added"))

    for name in base_props:
        if name not in target_props:
            changes.append(PropertyChange(name=name, change_type="removed"))

    for name in base_props:
        if name in target_props:
            bp = base_props[name]
            tp = target_props[name]
            if bp.type != tp.type or bp.is_key != tp.is_key:
                changes.append(PropertyChange(
                    name=name,
                    change_type="modified",
                    old_value=f"type={bp.type},key={bp.is_key}",
                    new_value=f"type={tp.type},key={tp.is_key}",
                ))

    return changes


def _diff_relationships(
    base: list[RelationshipType], target: list[RelationshipType]
) -> list[RelationshipTypeDiff]:
    base_map = {rt.name: rt for rt in base}
    target_map = {rt.name: rt for rt in target}
    diffs: list[RelationshipTypeDiff] = []

    for name in target_map:
        if name not in base_map:
            t = target_map[name]
            diffs.append(RelationshipTypeDiff(
                name=name,
                change_type="added",
                source_node=t.source_node,
                target_node=t.target_node,
            ))

    for name in base_map:
        if name not in target_map:
            b = base_map[name]
            diffs.append(RelationshipTypeDiff(
                name=name,
                change_type="removed",
                source_node=b.source_node,
                target_node=b.target_node,
            ))

    for name in base_map:
        if name in target_map:
            b = base_map[name]
            t = target_map[name]
            endpoint_changed = (
                b.source_node != t.source_node or b.target_node != t.target_node
            )
            prop_changes = _diff_rel_properties(b, t)
            if endpoint_changed or prop_changes:
                diffs.append(RelationshipTypeDiff(
                    name=name,
                    change_type="modified",
                    source_node=t.source_node,
                    target_node=t.target_node,
                    property_changes=prop_changes,
                    endpoint_changed=endpoint_changed,
                ))

    return diffs


def _diff_rel_properties(
    base: RelationshipType, target: RelationshipType
) -> list[PropertyChange]:
    base_props = {p.name: p for p in base.properties}
    target_props = {p.name: p for p in target.properties}
    changes: list[PropertyChange] = []

    for name in target_props:
        if name not in base_props:
            changes.append(PropertyChange(name=name, change_type="added"))

    for name in base_props:
        if name not in target_props:
            changes.append(PropertyChange(name=name, change_type="removed"))

    for name in base_props:
        if name in target_props:
            bp = base_props[name]
            tp = target_props[name]
            if bp.type != tp.type:
                changes.append(PropertyChange(
                    name=name,
                    change_type="modified",
                    old_value=bp.type,
                    new_value=tp.type,
                ))

    return changes


def _build_summary(
    node_diffs: list[NodeTypeDiff],
    rel_diffs: list[RelationshipTypeDiff],
) -> str:
    n_added = sum(1 for d in node_diffs if d.change_type == "added")
    n_removed = sum(1 for d in node_diffs if d.change_type == "removed")
    n_modified = sum(1 for d in node_diffs if d.change_type == "modified")
    r_added = sum(1 for d in rel_diffs if d.change_type == "added")
    r_removed = sum(1 for d in rel_diffs if d.change_type == "removed")
    r_modified = sum(1 for d in rel_diffs if d.change_type == "modified")

    parts = []
    if n_added:
        parts.append(f"nodes +{n_added}")
    if n_removed:
        parts.append(f"nodes -{n_removed}")
    if n_modified:
        parts.append(f"nodes ~{n_modified}")
    if r_added:
        parts.append(f"rels +{r_added}")
    if r_removed:
        parts.append(f"rels -{r_removed}")
    if r_modified:
        parts.append(f"rels ~{r_modified}")

    if not parts:
        return "No changes"
    return ", ".join(parts)
