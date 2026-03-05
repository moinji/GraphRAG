"""CSV parsing, validation, type coercion, and in-memory session management."""

from __future__ import annotations

import csv
import io
import random
import time

from app.models.schemas import CSVTableSummary, ERDSchema

# In-memory session store: session_id → { "data": {...}, "created_at": float }
SESSION_TTL = 3600  # seconds (1 hour)
MAX_SESSIONS = 50

_csv_sessions: dict[str, dict] = {}


def _cleanup_expired_sessions() -> None:
    """Remove sessions older than SESSION_TTL."""
    now = time.time()
    expired = [
        sid for sid, sess in _csv_sessions.items()
        if now - sess.get("created_at", 0) > SESSION_TTL
    ]
    for sid in expired:
        del _csv_sessions[sid]


def create_session(data: dict[str, list[dict]]) -> str:
    """Store parsed CSV data and return a session ID."""
    _cleanup_expired_sessions()
    # Evict oldest if at capacity
    while len(_csv_sessions) >= MAX_SESSIONS:
        oldest_id = min(_csv_sessions, key=lambda k: _csv_sessions[k].get("created_at", 0))
        del _csv_sessions[oldest_id]

    ts = int(time.time())
    rand = f"{random.randint(0, 0xFFFF):04x}"
    session_id = f"csv_{ts}_{rand}"
    _csv_sessions[session_id] = {"data": data, "created_at": time.time()}
    return session_id


def get_session(session_id: str) -> dict[str, list[dict]] | None:
    """Retrieve CSV data for a session."""
    _cleanup_expired_sessions()
    sess = _csv_sessions.get(session_id)
    if sess is None:
        return None
    return sess.get("data")


def delete_session(session_id: str) -> None:
    """Remove a session (one-time consumption)."""
    _csv_sessions.pop(session_id, None)


def parse_csv_files(
    files_data: list[tuple[str, bytes]],
    erd: ERDSchema,
) -> tuple[dict[str, list[dict]], list[CSVTableSummary], list[str], list[str]]:
    """Parse multiple CSV files against an ERD schema.

    Args:
        files_data: list of (filename, content_bytes) tuples
        erd: the ERD schema for validation

    Returns:
        (data_dict, summaries, errors, warnings)
        - data_dict: { table_name: [row_dicts] }
        - summaries: per-table summary info
        - errors: list of error messages (blocking)
        - warnings: list of non-blocking warning messages
    """
    erd_table_names = {t.name.lower() for t in erd.tables}
    data: dict[str, list[dict]] = {}
    summaries: list[CSVTableSummary] = []
    errors: list[str] = []
    global_warnings: list[str] = []
    seen_tables: set[str] = set()

    for filename, content in files_data:
        table_name, rows, columns, warnings, file_errors = _parse_single_csv(
            filename, content, erd
        )

        if file_errors:
            errors.extend(file_errors)
            continue

        # Validate table name exists in ERD
        if table_name.lower() not in erd_table_names:
            errors.append(
                f"{filename}: table '{table_name}' not found in ERD"
            )
            continue

        # Detect duplicate table uploads
        if table_name.lower() in seen_tables:
            errors.append(
                f"{filename}: duplicate CSV for table '{table_name}' (already uploaded)"
            )
            continue
        seen_tables.add(table_name.lower())

        data[table_name] = rows
        summaries.append(
            CSVTableSummary(
                table_name=table_name,
                row_count=len(rows),
                columns=columns,
                warnings=warnings,
            )
        )

    # Warn about ERD tables with no CSV data (non-blocking)
    uploaded_tables = {t.lower() for t in data}
    missing_tables = erd_table_names - uploaded_tables
    if missing_tables:
        for t in sorted(missing_tables):
            global_warnings.append(f"No CSV for table '{t}' — nodes will be empty")

    return data, summaries, errors, global_warnings


def _parse_single_csv(
    filename: str,
    content: bytes,
    erd: ERDSchema,
) -> tuple[str, list[dict], list[str], list[str], list[str]]:
    """Parse a single CSV file.

    Returns:
        (table_name, rows, columns, warnings, errors)
    """
    warnings: list[str] = []
    errors: list[str] = []

    # Derive table name from filename (strip .csv extension)
    if not filename.lower().endswith(".csv"):
        errors.append(f"{filename}: file must have .csv extension")
        return "", [], [], warnings, errors

    table_name = filename[:-4].lower()  # strip .csv + normalize to lowercase

    # Decode content (utf-8-sig strips BOM automatically)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{filename}: unable to decode file (use UTF-8)")
            return table_name, [], [], warnings, errors

    # Parse CSV
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        errors.append(f"{filename}: empty CSV (no header row)")
        return table_name, [], [], warnings, errors

    csv_columns = list(reader.fieldnames)

    # Get column type map from ERD
    col_type_map = _get_column_type_map(table_name, erd)

    # Identify extra columns not in DDL
    for col in csv_columns:
        if col.lower() not in col_type_map:
            warnings.append(f"{filename}: column '{col}' not in DDL (ignored)")

    rows: list[dict] = []
    raw_rows = list(reader)

    if len(raw_rows) == 0:
        errors.append(f"{filename}: CSV has header but no data rows")
        return table_name, [], [], warnings, errors

    for row_idx, row in enumerate(raw_rows, start=2):  # row 2+ (1-indexed, header=1)
        parsed_row: dict = {}
        row_has_error = False

        for col in csv_columns:
            raw_value = row.get(col, "")
            if raw_value is None:
                raw_value = ""

            # Skip columns not in DDL
            if col.lower() not in col_type_map:
                continue

            sql_type, nullable = col_type_map[col.lower()]

            try:
                parsed_row[col] = _coerce_value(raw_value, sql_type, nullable)
            except ValueError as e:
                errors.append(f"{filename} row {row_idx}, column '{col}': {e}")
                row_has_error = True

        if not row_has_error:
            rows.append(parsed_row)

    valid_columns = [c for c in csv_columns if c.lower() in col_type_map]
    return table_name, rows, valid_columns, warnings, errors


def _coerce_value(value: str, sql_type: str, nullable: bool) -> object:
    """Convert a CSV string value to the appropriate Python type.

    Type mapping:
        INT/INTEGER/SERIAL/BIGINT → int
        DECIMAL/NUMERIC/FLOAT/DOUBLE/REAL → float
        BOOL/BOOLEAN → bool
        everything else (VARCHAR, TEXT, DATE, TIMESTAMP, etc.) → str
        empty string + nullable → None
    """
    stripped = value.strip()

    # Handle empty/null values
    if stripped == "" or stripped.upper() == "NULL":
        if nullable:
            return None
        raise ValueError(f"empty value for non-nullable column")

    upper_type = sql_type.upper()

    # Integer types
    if any(
        t in upper_type
        for t in ("INT", "INTEGER", "SERIAL", "BIGINT", "SMALLINT")
    ):
        try:
            return int(stripped)
        except ValueError:
            raise ValueError(f"cannot convert '{stripped}' to integer")

    # Floating point types
    if any(
        t in upper_type
        for t in ("DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL")
    ):
        try:
            return float(stripped)
        except ValueError:
            raise ValueError(f"cannot convert '{stripped}' to float")

    # Boolean types
    if any(t in upper_type for t in ("BOOL", "BOOLEAN")):
        if stripped.lower() in ("true", "1", "yes", "t"):
            return True
        if stripped.lower() in ("false", "0", "no", "f"):
            return False
        raise ValueError(f"cannot convert '{stripped}' to boolean")

    # Everything else → string
    return stripped


def _get_primary_key(table_name: str, erd: ERDSchema) -> str | None:
    """Return the primary key column name for a table, or None."""
    for table in erd.tables:
        if table.name.lower() == table_name.lower():
            if table.primary_key:
                return table.primary_key
            # Fall back: look for is_primary_key flag in columns
            for col in table.columns:
                if col.is_primary_key:
                    return col.name
            return None
    return None


def _get_column_type_map(
    table_name: str, erd: ERDSchema
) -> dict[str, tuple[str, bool]]:
    """Build column_name(lower) → (data_type, nullable) mapping for a table."""
    for table in erd.tables:
        if table.name.lower() == table_name.lower():
            return {
                col.name.lower(): (col.data_type, col.nullable)
                for col in table.columns
            }
    return {}
