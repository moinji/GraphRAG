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

        table_node = statement.find(exp.Table)
        if table_node is None:
            continue
        table_name = table_node.name

        columns: list[ColumnInfo] = []
        pk_col: str | None = None

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
                pk_col = col_name

        tables.append(TableInfo(
            name=table_name,
            columns=columns,
            primary_key=pk_col,
        ))

    # ── Phase 2: regex for inline REFERENCES (reliable for all dialects) ─
    current_table: str | None = None
    for line in ddl_text.split("\n"):
        create_match = re.match(
            r"CREATE\s+TABLE\s+(\w+)", line, re.IGNORECASE
        )
        if create_match:
            current_table = create_match.group(1)
            continue

        if line.strip() in (");", ")"):
            current_table = None
            continue

        if current_table:
            ref_match = re.search(
                r"(\w+)\s+\w+.*?REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)",
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

    return ERDSchema(tables=tables, foreign_keys=foreign_keys)


def parse_ddl_file(path: str | Path) -> ERDSchema:
    """Read a .sql file and parse it."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_ddl(text)
