"""OWL API 엔드포인트 테스트."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_export_owl_disabled(client):
    """#1: enable_owl=False → 502."""
    resp = await client.get("/api/v1/owl/export/1")
    assert resp.status_code == 502
    assert "비활성화" in resp.json()["detail"]


@pytest.mark.anyio
async def test_export_owl_not_found(client, monkeypatch):
    """#2: 존재하지 않는 version_id → 404."""
    monkeypatch.setattr("app.config.settings.enable_owl", True)
    resp = await client.get("/api/v1/owl/export/99999")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_export_owl_success(client, monkeypatch, ecommerce_erd):
    """#3: 정상 export → 200 + turtle content."""
    monkeypatch.setattr("app.config.settings.enable_owl", True)
    # Generate ontology to create a version
    resp = await client.post("/api/v1/ontology/generate", json={
        "erd": ecommerce_erd.model_dump(), "skip_llm": True,
    })
    if resp.status_code != 200:
        pytest.skip("Ontology generation requires PG")
    version_id = resp.json().get("version_id")
    if version_id is None:
        pytest.skip("Version not persisted (PG unavailable)")

    resp = await client.get(f"/api/v1/owl/export/{version_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert data["triple_count"] > 0


@pytest.mark.anyio
async def test_validate_owl_disabled(client):
    """#4: enable_owl=False → 502."""
    resp = await client.post("/api/v1/owl/validate/1")
    assert resp.status_code == 502


@pytest.mark.anyio
async def test_validate_owl_success(client, monkeypatch, ecommerce_erd):
    """#5: 정상 validate → 200 + conforms."""
    monkeypatch.setattr("app.config.settings.enable_owl", True)
    resp = await client.post("/api/v1/ontology/generate", json={
        "erd": ecommerce_erd.model_dump(), "skip_llm": True,
    })
    if resp.status_code != 200:
        pytest.skip("Ontology generation requires PG")
    version_id = resp.json().get("version_id")
    if version_id is None:
        pytest.skip("Version not persisted (PG unavailable)")

    resp = await client.post(f"/api/v1/owl/validate/{version_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "conforms" in data
    assert data["level"] == "tbox"
