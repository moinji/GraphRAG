"""Ontology version API tests — 10 cases."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models.schemas import ERDSchema
from app.ontology.fk_rule_engine import build_ontology


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def _app():
    return create_app()


@pytest.fixture
async def api_client(_app):
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_version_row(
    version_id: int = 1,
    status: str = "draft",
    ontology_json: dict | None = None,
    eval_json: dict | None = None,
):
    """Helper to build a mock PG row dict."""
    return {
        "id": version_id,
        "erd_hash": "abc123" * 10 + "abcd",
        "ontology_json": ontology_json or {"node_types": [], "relationship_types": []},
        "eval_json": eval_json or {
            "critical_error_rate": 0.0,
            "fk_relationship_coverage": 1.0,
            "direction_accuracy": 1.0,
            "llm_adoption_rate": None,
            "node_count_generated": 9,
            "node_count_golden": 9,
            "relationship_count_generated": 12,
            "relationship_count_golden": 12,
        },
        "status": status,
        "created_at": "2026-02-25T10:00:00",
    }


# ════════════════════════════════════════════════════════════════════
#  GET /api/v1/ontology/versions/{version_id}
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_get_version_success(api_client: AsyncClient):
    """#1: GET existing version → 200 with ontology + status=draft."""
    row = _make_version_row()
    with patch("app.routers.ontology_versions.get_version", return_value=row):
        resp = await api_client.get("/api/v1/ontology/versions/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version_id"] == 1
    assert data["status"] == "draft"
    assert "ontology" in data
    assert "eval_report" in data


@pytest.mark.anyio
async def test_get_version_not_found(api_client: AsyncClient):
    """#2: GET non-existent version → 404."""
    with patch("app.routers.ontology_versions.get_version", return_value=None):
        resp = await api_client.get("/api/v1/ontology/versions/999")
    assert resp.status_code == 404
    assert "999" in resp.json()["detail"]


# ════════════════════════════════════════════════════════════════════
#  PUT /api/v1/ontology/versions/{version_id}
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_update_version_success(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#3: PUT valid ontology on draft version → 200, updated=true."""
    ontology = build_ontology(ecommerce_erd)
    row = _make_version_row(ontology_json=ontology.model_dump())
    body = {"ontology": ontology.model_dump()}

    with (
        patch("app.routers.ontology_versions.get_version", return_value=row),
        patch("app.routers.ontology_versions.update_version", return_value=True),
    ):
        resp = await api_client.put("/api/v1/ontology/versions/1", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] is True
    assert data["status"] == "draft"


@pytest.mark.anyio
async def test_update_version_not_found(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#4: PUT on non-existent version → 404."""
    ontology = build_ontology(ecommerce_erd)
    body = {"ontology": ontology.model_dump()}

    with patch("app.routers.ontology_versions.get_version", return_value=None):
        resp = await api_client.put("/api/v1/ontology/versions/999", json=body)
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_update_version_already_approved(
    api_client: AsyncClient, ecommerce_erd: ERDSchema
):
    """#5: PUT on approved version → 409."""
    ontology = build_ontology(ecommerce_erd)
    row = _make_version_row(status="approved")
    body = {"ontology": ontology.model_dump()}

    with patch("app.routers.ontology_versions.get_version", return_value=row):
        resp = await api_client.put("/api/v1/ontology/versions/1", json=body)
    assert resp.status_code == 409
    assert "approved" in resp.json()["detail"]


# ════════════════════════════════════════════════════════════════════
#  POST /api/v1/ontology/versions/{version_id}/approve
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_approve_version_success(api_client: AsyncClient):
    """#6: POST approve on draft version → 200, status=approved."""
    row = _make_version_row(status="draft")
    with (
        patch("app.routers.ontology_versions.get_version", return_value=row),
        patch("app.routers.ontology_versions.approve_version", return_value=True),
    ):
        resp = await api_client.post("/api/v1/ontology/versions/1/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["version_id"] == 1


@pytest.mark.anyio
async def test_approve_version_not_found(api_client: AsyncClient):
    """#7: POST approve on non-existent version → 404."""
    with patch("app.routers.ontology_versions.get_version", return_value=None):
        resp = await api_client.post("/api/v1/ontology/versions/999/approve")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_approve_version_already_approved(api_client: AsyncClient):
    """#8: POST approve on already-approved version → 409."""
    row = _make_version_row(status="approved")
    with patch("app.routers.ontology_versions.get_version", return_value=row):
        resp = await api_client.post("/api/v1/ontology/versions/1/approve")
    assert resp.status_code == 409
    assert "approved" in resp.json()["detail"]


# ════════════════════════════════════════════════════════════════════
#  Validation & Evaluation Re-calculation
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_update_version_invalid_body(api_client: AsyncClient):
    """#9: PUT with invalid JSON body → 422."""
    row = _make_version_row()
    with patch("app.routers.ontology_versions.get_version", return_value=row):
        resp = await api_client.put(
            "/api/v1/ontology/versions/1",
            json={"bad_field": "value"},
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_recalculates_eval(
    api_client: AsyncClient, ecommerce_erd: ERDSchema
):
    """#10: PUT re-calculates eval_json from the updated ontology."""
    ontology = build_ontology(ecommerce_erd)
    row = _make_version_row(ontology_json=ontology.model_dump())

    captured_eval = {}

    def mock_update(_vid, _ontology_json, eval_json, **kwargs):
        captured_eval["data"] = eval_json
        return True

    body = {"ontology": ontology.model_dump()}
    with (
        patch("app.routers.ontology_versions.get_version", return_value=row),
        patch(
            "app.routers.ontology_versions.update_version",
            side_effect=mock_update,
        ),
    ):
        resp = await api_client.put("/api/v1/ontology/versions/1", json=body)

    assert resp.status_code == 200
    # Verify eval was re-calculated (perfect score for golden-matching ontology)
    assert captured_eval["data"]["critical_error_rate"] == 0.0
    assert captured_eval["data"]["fk_relationship_coverage"] == 1.0
    assert captured_eval["data"]["direction_accuracy"] == 1.0
