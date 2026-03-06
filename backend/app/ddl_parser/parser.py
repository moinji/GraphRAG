"""DDL parser using sqlglot + regex fallback for FK extraction."""

from __future__ import annotations

import re
from pathlib import Path

import sqlglot
from sqlglot import exp

from app.models.schemas import ColumnInfo, ERDSchema, ForeignKey, TableInfo


def _sql_type_str(kind_node) -> str:
    """Convert sqlglot type node to a simple string."""
    if kind_node is None:
        return "unknown"
    return kind_node.sql(dialect="postgres")


def parse_ddl(ddl_text: str) -> ERDSchema:
    """Parse DDL text into an ERDSchema with tables and foreign keys."""
    tables: list[TableInfo] = []
    foreign_keys: list[ForeignKey] = []

    # ── Phase 1: sqlglot AST for table / column structure ──────────
    for statement in sqlglot.parse(ddl_text, read="postgres"):
        if not isinstance(statement, exp.Create):
            continue

        # Skip VIEW, TYPE, ENUM, INDEX etc. — only process TABLE
        kind = statement.args.get("kind")
        if kind and kind.upper() != "TABLE":
            continue

        table_node = statement.find(exp.Table)
        if table_node is None:
            continue
        # Strip schema prefix (e.g. "public.customers" → "customers")
        table_name = table_node.name

        columns: list[ColumnInfo] = []
        pk_cols: list[str] = []

        for col_def in statement.find_all(exp.ColumnDef):
            col_name = col_def.name
            col_type = _sql_type_str(col_def.args.get("kind"))

            is_pk = False
            nullable = True

            # SERIAL type implies PRIMARY KEY
            if "SERIAL" in col_type.upper():
                is_pk = True
                nullable = False

            for constraint in col_def.find_all(exp.ColumnConstraint):
                if constraint.find(exp.PrimaryKeyColumnConstraint):
                    is_pk = True
                    nullable = False
                if constraint.find(exp.NotNullColumnConstraint):
                    nullable = False

            columns.append(ColumnInfo(
                name=col_name,
                data_type=col_type,
                nullable=nullable,
                is_primary_key=is_pk,
            ))

            if is_pk:
                pk_cols.append(col_name)

        # Phase 1b: detect table-level PRIMARY KEY (composite)
        for node in statement.find_all(exp.PrimaryKey):
            composite_cols = [col.name for col in node.find_all(exp.Column)]
            if composite_cols:
                pk_cols = composite_cols
                # Mark columns as PK
                for col in columns:
                    if col.name in composite_cols:
                        col.is_primary_key = True
                        col.nullable = False

        tables.append(TableInfo(
            name=table_name,
            columns=columns,
            primary_key=pk_cols[0] if pk_cols else None,
            primary_keys=pk_cols,
        ))

    # ── Phase 2: regex for inline REFERENCES + composite PK ─────────
    current_table: str | None = None
    for line in ddl_text.split("\n"):
        # Skip VIEW/TYPE/ENUM lines
        if re.match(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:VIEW|TYPE|ENUM|INDEX|SEQUENCE|FUNCTION|TRIGGER)\b", line, re.IGNORECASE):
            current_table = None
            continue

        # Match CREATE TABLE with optional IF NOT EXISTS and schema prefix
        create_match = re.match(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\"?\w+\"?\.)?\"?(\w+)\"?", line, re.IGNORECASE
        )
        if create_match:
            current_table = create_match.group(1)
            continue

        if line.strip() in (");", ")"):
            current_table = None
            continue

        if current_table:
            # FK references
            ref_match = re.search(
                r"(\w+)\s+\w+.*?REFERENCES\s+(?:\w+\.)?(\w+)\s*\(\s*(\w+)\s*\)",
                line,
                re.IGNORECASE,
            )
            if ref_match:
                foreign_keys.append(ForeignKey(
                    source_table=current_table,
                    source_column=ref_match.group(1),
                    target_table=ref_match.group(2),
                    target_column=ref_match.group(3),
                ))

            # Composite PRIMARY KEY (regex fallback for sqlglot misses)
            pk_match = re.match(
                r"\s*PRIMARY\s+KEY\s*\(([^)]+)\)",
                line,
                re.IGNORECASE,
            )
            if pk_match:
                pk_col_names = [c.strip() for c in pk_match.group(1).split(",")]
                # Update the matching table
                for table in tables:
                    if table.name == current_table and not table.primary_keys:
                        table.primary_keys = pk_col_names
                        if not table.primary_key:
                            table.primary_key = pk_col_names[0]
                        for col in table.columns:
                            if col.name in pk_col_names:
                                col.is_primary_key = True
                                col.nullable = False

    return ERDSchema(tables=tables, foreign_keys=foreign_keys)


def parse_ddl_file(path: str | Path) -> ERDSchema:
    """Read a .sql file and parse it."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_ddl(text)
