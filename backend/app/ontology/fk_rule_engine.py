"""FK rule-based ontology engine: ERDSchema → OntologySpec.

Known tables use fixed rules (e-commerce PoC).
Unknown tables are auto-mapped: table_name → PascalCase node label,
FK columns → relationships with auto-generated names.
"""

from __future__ import annotations

from app.models.schemas import (
    ERDSchema,
    ForeignKey,
    NodeProperty,
    NodeType,
    OntologySpec,
    RelProperty,
    RelationshipType,
)

# ── Constants ──────────────────────────────────────────────────────

TABLE_TO_LABEL: dict[str, str] = {
    "addresses": "Address",
    "categories": "Category",
    "suppliers": "Supplier",
    "coupons": "Coupon",
    "customers": "Customer",
    "products": "Product",
    "orders": "Order",
    "payments": "Payment",
    "reviews": "Review",
}

# Tables that become *relationships* rather than nodes.
JOIN_TABLE_CONFIG: dict[str, dict] = {
    "order_items": {
        "rel_name": "CONTAINS",
        "source_fk_col": "order_id",
        "target_fk_col": "product_id",
        "property_columns": ["quantity", "unit_price"],
    },
    "wishlists": {
        "rel_name": "WISHLISTED",
        "source_fk_col": "customer_id",
        "target_fk_col": "product_id",
        "property_columns": [],
    },
    "shipping": {
        "rel_name": "SHIPPED_TO",
        "source_fk_col": "order_id",
        "target_fk_col": "address_id",
        "property_columns": ["carrier", "tracking_number", "status"],
    },
}

# Direct FK → relationship mapping.
# Key: (fk_source_table, fk_source_column)
# Value: (source_node_label, rel_name, target_node_label,
#         source_key_col_in_data, target_key_col_in_data)
# source_key_col / target_key_col tell the loader *which column in the
# FK-owning table* identifies the source and target nodes respectively.
DIRECTION_MAP: dict[tuple[str, str], tuple[str, str, str, str, str]] = {
    # FK-owning table IS the source node  (normal FK direction)
    ("customers", "address_id"):  ("Customer", "LIVES_AT",    "Address",  "id", "address_id"),
    ("products", "category_id"):  ("Product",  "BELONGS_TO",  "Category", "id", "category_id"),
    ("products", "supplier_id"):  ("Product",  "SUPPLIED_BY", "Supplier", "id", "supplier_id"),
    ("orders", "coupon_id"):      ("Order",    "USED_COUPON", "Coupon",   "id", "coupon_id"),
    ("reviews", "product_id"):    ("Review",   "REVIEWS",     "Product",  "id", "product_id"),
    # FK-owning table is the TARGET node  (flipped direction)
    ("orders", "customer_id"):    ("Customer", "PLACED",      "Order",    "customer_id", "id"),
    ("payments", "order_id"):     ("Order",    "PAID_BY",     "Payment",  "order_id", "id"),
    ("reviews", "customer_id"):   ("Customer", "WROTE",       "Review",   "customer_id", "id"),
    # Self-referential (parent → child)
    ("categories", "parent_id"):  ("Category", "PARENT_OF",   "Category", "parent_id", "id"),
}

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


def build_ontology(erd: ERDSchema) -> OntologySpec:
    """Convert ERDSchema → OntologySpec using fixed FK rules.

    Known e-commerce tables use hardcoded mappings.
    Unknown tables are auto-mapped: table_name → PascalCase node label,
    FK columns → auto-named relationships.
    """
    table_map = {t.name: t for t in erd.tables}
    node_types: list[NodeType] = []
    relationship_types: list[RelationshipType] = []

    # Build a unified label map: known tables + auto-mapped unknown tables
    label_map: dict[str, str] = dict(TABLE_TO_LABEL)
    for table in erd.tables:
        if table.name not in label_map and table.name not in JOIN_TABLE_CONFIG:
            label_map[table.name] = _to_pascal_case(table.name)

    # ── 1. Node types ─────────────────────────────────────────────
    for table in erd.tables:
        if table.name in JOIN_TABLE_CONFIG:
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

        # Try hardcoded mapping first
        if key in DIRECTION_MAP:
            src_label, rel_name, tgt_label, src_key, tgt_key = DIRECTION_MAP[key]
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
        if fk.source_table in JOIN_TABLE_CONFIG:
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
    for jt_name, cfg in JOIN_TABLE_CONFIG.items():
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
