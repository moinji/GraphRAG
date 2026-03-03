"""API integration tests for DDL upload endpoint."""

from __future__ import annotations

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
