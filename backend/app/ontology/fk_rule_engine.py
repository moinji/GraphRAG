"""FK rule-based ontology engine: ERDSchema → OntologySpec.

Two-layer approach:
1. Domain hints (optional): known table→label, FK→relationship overrides.
2. Auto-mapping (universal): PascalCase labels, auto join-table detection,
   auto-generated relationship names for any DDL.

Domain hints are loaded from domain_hints.py and auto-detected from ERD.
"""

from __future__ import annotations

import logging

from app.models.schemas import (
    ERDSchema,
    ForeignKey,
    NodeProperty,
    NodeType,
    OntologySpec,
    RelProperty,
    RelationshipType,
    TableInfo,
)
from app.ontology.domain_hints import DomainHint, detect_domain

logger = logging.getLogger(__name__)

SQL_TYPE_MAP: dict[str, str] = {
    "SERIAL": "integer",
    "INTEGER": "integer",
    "INT": "integer",
    "BIGINT": "integer",
    "SMALLINT": "integer",
    "VARCHAR": "string",
    "TEXT": "string",
    "CHAR": "string",
    "DECIMAL": "float",
    "NUMERIC": "float",
    "FLOAT": "float",
    "DOUBLE": "float",
    "BOOLEAN": "boolean",
    "BOOL": "boolean",
    "TIMESTAMP": "string",
    "DATE": "string",
    "TIME": "string",
}


def _map_sql_type(sql_type: str) -> str:
    """Map a SQL type string to a simple property type."""
    upper = sql_type.upper().split("(")[0].strip()
    return SQL_TYPE_MAP.get(upper, "string")


def _to_pascal_case(name: str) -> str:
    """Convert snake_case table name to PascalCase label.

    Examples: 'journal_entry' → 'JournalEntry', 'department' → 'Department'
    """
    return "".join(part.capitalize() for part in name.split("_"))


def _auto_rel_name(source_label: str, target_label: str, fk_col: str) -> str:
    """Generate a relationship name from FK column.

    Examples: 'department_id' → 'HAS_DEPARTMENT', 'parent_id' → 'PARENT_OF'
    """
    col_base = fk_col.removesuffix("_id").upper()
    if col_base == "PARENT":
        return "PARENT_OF"
    return f"HAS_{col_base}"


def _fk_columns_for_table(
    table_name: str, foreign_keys: list[ForeignKey]
) -> set[str]:
    """Return the set of FK column names for a given table."""
    return {
        fk.source_column
        for fk in foreign_keys
        if fk.source_table == table_name
    }


def _detect_join_tables(
    erd: ERDSchema,
    hint_join_config: dict[str, dict],
) -> dict[str, dict]:
    """Auto-detect join/bridge tables not covered by domain hint config.

    A table is treated as a join table when:
    - It has exactly 2 FK columns
    - Every non-PK, non-FK column is a candidate relationship property
      (i.e., the table exists primarily to link two entities)
    - It is not already in the hint config

    Returns a dict matching join table config format.
    """
    detected: dict[str, dict] = {}
    for table in erd.tables:
        if table.name in hint_join_config:
            continue

        fk_cols = _fk_columns_for_table(table.name, erd.foreign_keys)
        if len(fk_cols) != 2:
            continue

        # Get the two FKs
        table_fks = [fk for fk in erd.foreign_keys if fk.source_table == table.name]
        if len(table_fks) != 2:
            continue

        # Non-FK, non-PK columns become relationship properties
        pk_cols = set(table.primary_keys) if table.primary_keys else (
            {table.primary_key} if table.primary_key else set()
        )
        prop_cols = [
            c.name for c in table.columns
            if c.name not in fk_cols and c.name not in pk_cols
        ]

        # Heuristic: if there are 3+ non-FK/non-PK columns, it's likely
        # a real entity table, not a bridge/join table
        if len(prop_cols) > 2:
            continue

        fk0, fk1 = table_fks[0], table_fks[1]
        # Generate relationship name from table name
        rel_name = table.name.upper().removesuffix("S")

        detected[table.name] = {
            "rel_name": rel_name,
            "source_fk_col": fk0.source_column,
            "target_fk_col": fk1.source_column,
            "property_columns": prop_cols,
        }
        logger.info(
            "Auto-detected join table: %s → %s(%s, %s)",
            table.name, rel_name, fk0.source_column, fk1.source_column,
        )

    return detected


def build_ontology(
    erd: ERDSchema,
    domain_hint: DomainHint | None = None,
) -> OntologySpec:
    """Convert ERDSchema → OntologySpec using FK rules + auto-detection.

    If domain_hint is None, auto-detects the domain from ERD table names.
    Known tables use domain hints (pluggable mappings).
    Unknown tables are auto-mapped: table_name → PascalCase node label,
    FK columns → auto-named relationships.
    Join tables are auto-detected when not in the domain hint config.
    """
    # Auto-detect domain if not explicitly provided
    if domain_hint is None:
        domain_hint = detect_domain(erd)

    # Get domain-specific configs (empty if no domain matched)
    table_to_label = domain_hint.table_to_label if domain_hint else {}
    hint_join_config = domain_hint.join_table_config if domain_hint else {}
    direction_map = domain_hint.direction_map if domain_hint else {}

    table_map = {t.name: t for t in erd.tables}
    node_types: list[NodeType] = []
    relationship_types: list[RelationshipType] = []

    # Merge domain hint + auto-detected join tables
    all_join_config = dict(hint_join_config)
    all_join_config.update(_detect_join_tables(erd, hint_join_config))

    # Build a unified label map: domain hints + auto-mapped unknown tables
    label_map: dict[str, str] = dict(table_to_label)
    for table in erd.tables:
        if table.name not in label_map and table.name not in all_join_config:
            label_map[table.name] = _to_pascal_case(table.name)

    # ── 1. Node types ─────────────────────────────────────────────
    for table in erd.tables:
        if table.name in all_join_config:
            continue
        label = label_map.get(table.name)
        if label is None:
            continue

        fk_cols = _fk_columns_for_table(table.name, erd.foreign_keys)
        props: list[NodeProperty] = []
        for col in table.columns:
            if col.name in fk_cols:
                continue  # FK columns are expressed as relationships
            props.append(NodeProperty(
                name=col.name,
                source_column=col.name,
                type=_map_sql_type(col.data_type),
                is_key=col.is_primary_key,
            ))

        node_types.append(NodeType(
            name=label,
            source_table=table.name,
            properties=props,
        ))

    # ── 2. Direct FK relationships ────────────────────────────────
    for fk in erd.foreign_keys:
        key = (fk.source_table, fk.source_column)

        # Try domain hint mapping first
        if key in direction_map:
            src_label, rel_name, tgt_label, src_key, tgt_key = direction_map[key]
            relationship_types.append(RelationshipType(
                name=rel_name,
                source_node=src_label,
                target_node=tgt_label,
                data_table=fk.source_table,
                source_key_column=src_key,
                target_key_column=tgt_key,
                derivation="fk_direct",
            ))
            continue

        # Skip join table FKs (handled below)
        if fk.source_table in all_join_config:
            continue

        # Auto-map: FK-owning table → target table
        src_label = label_map.get(fk.source_table)
        tgt_label = label_map.get(fk.target_table)
        if src_label is None or tgt_label is None:
            continue

        # Self-referential FK (e.g. parent_id)
        if fk.source_table == fk.target_table:
            rel_name = _auto_rel_name(src_label, tgt_label, fk.source_column)
            relationship_types.append(RelationshipType(
                name=rel_name,
                source_node=src_label,
                target_node=tgt_label,
                data_table=fk.source_table,
                source_key_column=fk.source_column,
                target_key_column="id",
                derivation="fk_direct",
            ))
        else:
            rel_name = _auto_rel_name(src_label, tgt_label, fk.source_column)
            relationship_types.append(RelationshipType(
                name=rel_name,
                source_node=src_label,
                target_node=tgt_label,
                data_table=fk.source_table,
                source_key_column="id",
                target_key_column=fk.source_column,
                derivation="fk_direct",
            ))

    # ── 3. Join-table relationships ───────────────────────────────
    for jt_name, cfg in all_join_config.items():
        jt = table_map.get(jt_name)
        if jt is None:
            continue

        # Resolve source/target node labels from FK references
        fk_map: dict[str, ForeignKey] = {}
        for fk in erd.foreign_keys:
            if fk.source_table == jt_name:
                fk_map[fk.source_column] = fk

        src_fk = fk_map.get(cfg["source_fk_col"])
        tgt_fk = fk_map.get(cfg["target_fk_col"])
        if src_fk is None or tgt_fk is None:
            continue

        src_label = label_map.get(src_fk.target_table)
        tgt_label = label_map.get(tgt_fk.target_table)
        if src_label is None or tgt_label is None:
            continue

        # Build relationship properties from non-FK, non-PK columns
        rel_props: list[RelProperty] = []
        for col_name in cfg["property_columns"]:
            col_info = next(
                (c for c in jt.columns if c.name == col_name), None
            )
            rel_props.append(RelProperty(
                name=col_name,
                source_column=col_name,
                type=_map_sql_type(col_info.data_type) if col_info else "string",
            ))

        relationship_types.append(RelationshipType(
            name=cfg["rel_name"],
            source_node=src_label,
            target_node=tgt_label,
            data_table=jt_name,
            source_key_column=cfg["source_fk_col"],
            target_key_column=cfg["target_fk_col"],
            properties=rel_props,
            derivation="fk_join_table",
        ))

    return OntologySpec(
        node_types=node_types,
        relationship_types=relationship_types,
    )
