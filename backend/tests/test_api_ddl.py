"""API integration tests for DDL upload + NL→DDL endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app

ECOMMERCE_DDL_PATH = "demo_ecommerce.sql"


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_upload_valid_ddl(client: AsyncClient):
    from pathlib import Path

    ddl_bytes = Path(__file__).resolve().parent.parent.parent.joinpath(
        "examples", "schemas", "demo_ecommerce.sql"
    ).read_bytes()

    resp = await client.post(
        "/api/v1/ddl/upload",
        files={"file": ("demo.sql", ddl_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tables"]) == 12
    assert len(body["foreign_keys"]) == 15


@pytest.mark.anyio
async def test_upload_empty_file(client: AsyncClient):
    resp = await client.post(
        "/api/v1/ddl/upload",
        files={"file": ("empty.sql", b"", "application/octet-stream")},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_upload_binary_file(client: AsyncClient):
    binary_data = bytes(range(256))
    resp = await client.post(
        "/api/v1/ddl/upload",
        files={"file": ("bad.sql", binary_data, "application/octet-stream")},
    )
    assert resp.status_code == 422


# ════════════════════════════════════════════════════════════════════
#  NL → DDL
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_nl_to_ddl_success(client: AsyncClient):
    """NL→DDL returns generated DDL + parsed ERD."""
    mock_ddl = (
        "CREATE TABLE customers (id SERIAL PRIMARY KEY, name VARCHAR(100));\n"
        "CREATE TABLE orders (id SERIAL PRIMARY KEY, customer_id INT REFERENCES customers(id));"
    )
    with patch("app.ddl_parser.nl_to_ddl.generate_ddl_from_nl", return_value=mock_ddl):
        resp = await client.post(
            "/api/v1/ddl/generate-from-nl",
            json={"description": "온라인 쇼핑몰"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "CREATE TABLE" in body["ddl"]
    assert body["erd"] is not None
    assert len(body["erd"]["tables"]) == 2


@pytest.mark.anyio
async def test_nl_to_ddl_no_api_key(client: AsyncClient):
    """NL→DDL without API key returns 422."""
    with patch("app.ddl_parser.nl_to_ddl.settings") as mock_settings:
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None
        resp = await client.post(
            "/api/v1/ddl/generate-from-nl",
            json={"description": "테스트"},
        )
    assert resp.status_code == 422


def test_clean_ddl_strips_fences():
    """_clean_ddl removes markdown code fences."""
    from app.ddl_parser.nl_to_ddl import _clean_ddl

    raw = "```sql\nCREATE TABLE x (id INT);\n```"
    assert _clean_ddl(raw) == "CREATE TABLE x (id INT);"


def test_clean_ddl_no_fences():
    """_clean_ddl returns plain DDL unchanged."""
    from app.ddl_parser.nl_to_ddl import _clean_ddl

    raw = "CREATE TABLE x (id INT);"
    assert _clean_ddl(raw) == "CREATE TABLE x (id INT);"
