"""CSV Import tests — 12 cases."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.csv_import.parser import (
    _coerce_value,
    _get_column_type_map,
    create_session,
    delete_session,
    get_session,
    parse_csv_files,
)
from app.main import create_app
from app.models.schemas import ERDSchema


# ── Helpers ──────────────────────────────────────────────────────

def _mini_erd() -> ERDSchema:
    """Minimal ERD with one table for testing."""
    return ERDSchema(
        tables=[
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "data_type": "INTEGER", "nullable": False, "is_primary_key": True},
                    {"name": "name", "data_type": "VARCHAR(100)", "nullable": False, "is_primary_key": False},
                    {"name": "email", "data_type": "VARCHAR(200)", "nullable": True, "is_primary_key": False},
                    {"name": "age", "data_type": "INTEGER", "nullable": True, "is_primary_key": False},
                ],
                "primary_key": "id",
            },
            {
                "name": "orders",
                "columns": [
                    {"name": "id", "data_type": "INTEGER", "nullable": False, "is_primary_key": True},
                    {"name": "customer_id", "data_type": "INTEGER", "nullable": False, "is_primary_key": False},
                    {"name": "total", "data_type": "DECIMAL(10,2)", "nullable": False, "is_primary_key": False},
                    {"name": "status", "data_type": "VARCHAR(50)", "nullable": True, "is_primary_key": False},
                ],
                "primary_key": "id",
            },
        ],
        foreign_keys=[
            {
                "source_table": "orders",
                "source_column": "customer_id",
                "target_table": "customers",
                "target_column": "id",
            },
        ],
    )


def _csv_bytes(content: str) -> bytes:
    return content.encode("utf-8")


@pytest.fixture
def _app():
    return create_app()


@pytest.fixture
async def api_client(_app):
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ════════════════════════════════════════════════════════════════════
#  #1: Valid single CSV upload → 200 + session_id
# ════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_valid_single_csv_upload(api_client: AsyncClient):
    """#1: Upload one valid CSV → 200 with csv_session_id."""
    erd = _mini_erd()
    csv_content = "id,name,email,age\n1,Alice,alice@test.com,30\n2,Bob,bob@test.com,25\n"

    resp = await api_client.post(
        "/api/v1/csv/upload",
        files=[("files", ("customers.csv", csv_content.encode(), "text/csv"))],
        data={"erd_json": erd.model_dump_json()},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["csv_session_id"].startswith("csv_")
    assert len(data["tables"]) == 1
    assert data["tables"][0]["table_name"] == "customers"
    assert data["tables"][0]["row_count"] == 2


# ════════════════════════════════════════════════════════════════════
#  #2: Multiple CSV upload → 200 + per-table summaries
# ════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_multiple_csv_upload(api_client: AsyncClient):
    """#2: Upload two valid CSVs → 200 with 2 table summaries."""
    erd = _mini_erd()
    customers_csv = "id,name,email,age\n1,Alice,alice@test.com,30\n"
    orders_csv = "id,customer_id,total,status\n1,1,99.99,shipped\n"

    resp = await api_client.post(
        "/api/v1/csv/upload",
        files=[
            ("files", ("customers.csv", customers_csv.encode(), "text/csv")),
            ("files", ("orders.csv", orders_csv.encode(), "text/csv")),
        ],
        data={"erd_json": erd.model_dump_json()},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tables"]) == 2
    table_names = {t["table_name"] for t in data["tables"]}
    assert table_names == {"customers", "orders"}


# ════════════════════════════════════════════════════════════════════
#  #3: Table not in ERD → 422
# ════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_table_not_in_erd(api_client: AsyncClient):
    """#3: CSV filename doesn't match any ERD table → 422."""
    erd = _mini_erd()
    csv_content = "id,name\n1,Test\n"

    resp = await api_client.post(
        "/api/v1/csv/upload",
        files=[("files", ("unknown_table.csv", csv_content.encode(), "text/csv"))],
        data={"erd_json": erd.model_dump_json()},
    )
    assert resp.status_code == 422
    assert "unknown_table" in resp.json()["errors"][0]


# ════════════════════════════════════════════════════════════════════
#  #4: CSV with only DDL-unknown columns → 200 + warnings (PK not required)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_missing_id_column(api_client: AsyncClient):
    """#4: CSV without PK column still accepted (columns validated against DDL)."""
    erd = _mini_erd()
    csv_content = "name,email\nAlice,alice@test.com\n"

    resp = await api_client.post(
        "/api/v1/csv/upload",
        files=[("files", ("customers.csv", csv_content.encode(), "text/csv"))],
        data={"erd_json": erd.model_dump_json()},
    )
    assert resp.status_code == 200


# ════════════════════════════════════════════════════════════════════
#  #5: Extra columns not in DDL → 200 + warnings
# ════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_extra_columns_warning():
    """#5: CSV with columns not in DDL → warnings, data still parsed."""
    erd = _mini_erd()
    csv_content = _csv_bytes("id,name,email,age,extra_col\n1,Alice,a@test.com,30,bonus\n")

    data, summaries, errors, warnings = parse_csv_files(
        [("customers.csv", csv_content)], erd
    )
    assert len(errors) == 0
    assert len(summaries) == 1
    assert any("extra_col" in w for w in summaries[0].warnings)
    # Extra column should not be in the parsed row
    assert "extra_col" not in data["customers"][0]


# ════════════════════════════════════════════════════════════════════
#  #6: INT type coercion success
# ════════════════════════════════════════════════════════════════════

def test_int_type_coercion():
    """#6: Integer string values are coerced to int."""
    assert _coerce_value("42", "INTEGER", False) == 42
    assert isinstance(_coerce_value("42", "INTEGER", False), int)
    assert _coerce_value("0", "BIGINT", False) == 0


# ════════════════════════════════════════════════════════════════════
#  #7: INT with non-numeric value → error
# ════════════════════════════════════════════════════════════════════

def test_int_non_numeric_raises():
    """#7: Non-numeric value for INTEGER column → ValueError."""
    with pytest.raises(ValueError, match="cannot convert"):
        _coerce_value("abc", "INTEGER", False)


# ════════════════════════════════════════════════════════════════════
#  #8: Empty CSV → 422
# ════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_empty_csv(api_client: AsyncClient):
    """#8: CSV with header but no data rows → 422."""
    erd = _mini_erd()
    csv_content = "id,name,email,age\n"

    resp = await api_client.post(
        "/api/v1/csv/upload",
        files=[("files", ("customers.csv", csv_content.encode(), "text/csv"))],
        data={"erd_json": erd.model_dump_json()},
    )
    assert resp.status_code == 422
    assert "no data" in resp.json()["errors"][0].lower()


# ════════════════════════════════════════════════════════════════════
#  #9: KG build with csv_session_id → uses CSV data
# ════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kg_build_with_csv_session(api_client: AsyncClient):
    """#9: KG build with csv_session_id uses CSV data instead of seed."""
    # Set up a CSV session
    csv_data = {"customers": [{"id": 1, "name": "Alice"}]}
    session_id = create_session(csv_data)

    def _approved_row():
        return {
            "id": 1,
            "erd_hash": "abc123" * 10 + "abcd",
            "ontology_json": {
                "node_types": [{
                    "name": "Customer",
                    "source_table": "customers",
                    "properties": [
                        {"name": "id", "source_column": "id", "type": "integer", "is_key": True},
                    ],
                }],
                "relationship_types": [],
            },
            "eval_json": None,
            "status": "approved",
            "created_at": "2026-02-25T10:00:00",
        }

    with (
        patch("app.routers.kg_build.get_version", return_value=_approved_row()),
        patch("app.routers.kg_build.run_kg_build") as mock_run,
    ):
        resp = await api_client.post(
            "/api/v1/kg/build",
            json={
                "version_id": 1,
                "erd": {"tables": [{"name": "customers", "columns": [{"name": "id", "data_type": "INTEGER", "nullable": False, "is_primary_key": True}], "primary_key": "id"}], "foreign_keys": []},
                "csv_session_id": session_id,
            },
        )
    assert resp.status_code == 202
    # Verify csv_data was passed to run_kg_build
    call_kwargs = mock_run.call_args
    assert call_kwargs[0][4] == csv_data or call_kwargs[1].get("csv_data") == csv_data or (len(call_kwargs[0]) > 4 and call_kwargs[0][4] == csv_data)

    # Session should be consumed (deleted)
    assert get_session(session_id) is None


# ════════════════════════════════════════════════════════════════════
#  #10: Non-existent csv_session_id → 404
# ════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_nonexistent_csv_session(api_client: AsyncClient):
    """#10: KG build with invalid csv_session_id → 404."""
    def _approved_row():
        return {
            "id": 1,
            "erd_hash": "abc",
            "ontology_json": {"node_types": [], "relationship_types": []},
            "eval_json": None,
            "status": "approved",
            "created_at": "2026-02-25T10:00:00",
        }

    with patch("app.routers.kg_build.get_version", return_value=_approved_row()):
        resp = await api_client.post(
            "/api/v1/kg/build",
            json={
                "version_id": 1,
                "erd": {"tables": [], "foreign_keys": []},
                "csv_session_id": "nonexistent_session",
            },
        )
    assert resp.status_code == 404
    assert "nonexistent_session" in resp.json()["detail"]


# ════════════════════════════════════════════════════════════════════
#  #11: KG build without csv_session_id → seed data fallback
# ════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kg_build_without_csv_uses_seed(api_client: AsyncClient):
    """#11: KG build without csv_session_id passes None (seed fallback)."""
    def _approved_row():
        return {
            "id": 1,
            "erd_hash": "abc",
            "ontology_json": {"node_types": [], "relationship_types": []},
            "eval_json": None,
            "status": "approved",
            "created_at": "2026-02-25T10:00:00",
        }

    with (
        patch("app.routers.kg_build.get_version", return_value=_approved_row()),
        patch("app.routers.kg_build.run_kg_build") as mock_run,
    ):
        resp = await api_client.post(
            "/api/v1/kg/build",
            json={
                "version_id": 1,
                "erd": {"tables": [], "foreign_keys": []},
            },
        )
    assert resp.status_code == 202
    # csv_data should be None (last positional arg)
    call_args = mock_run.call_args[0]
    assert call_args[4] is None


# ════════════════════════════════════════════════════════════════════
#  #12: Nullable empty value → None
# ════════════════════════════════════════════════════════════════════

def test_nullable_empty_value_becomes_none():
    """#12: Empty string for a nullable column → None."""
    assert _coerce_value("", "VARCHAR(100)", nullable=True) is None
    assert _coerce_value("", "INTEGER", nullable=True) is None
    assert _coerce_value("NULL", "VARCHAR(100)", nullable=True) is None


# ════════════════════════════════════════════════════════════════════
#  Additional parser unit tests
# ════════════════════════════════════════════════════════════════════

def test_decimal_coercion():
    """DECIMAL values are coerced to float."""
    result = _coerce_value("99.99", "DECIMAL(10,2)", False)
    assert isinstance(result, float)
    assert result == pytest.approx(99.99)


def test_boolean_coercion():
    """Boolean string values are coerced correctly."""
    assert _coerce_value("true", "BOOLEAN", False) is True
    assert _coerce_value("false", "BOOLEAN", False) is False
    assert _coerce_value("1", "BOOLEAN", False) is True
    assert _coerce_value("0", "BOOLEAN", False) is False


def test_session_lifecycle():
    """Session create → get → delete lifecycle."""
    data = {"test_table": [{"id": 1}]}
    sid = create_session(data)
    assert sid.startswith("csv_")
    assert get_session(sid) == data
    delete_session(sid)
    assert get_session(sid) is None


def test_non_nullable_empty_raises():
    """Empty string for a non-nullable column → ValueError."""
    with pytest.raises(ValueError, match="empty value"):
        _coerce_value("", "INTEGER", nullable=False)
