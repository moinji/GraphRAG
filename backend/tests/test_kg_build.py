"""KG Build API tests — 10 cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models.schemas import ERDSchema


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def _app():
    return create_app()


@pytest.fixture
async def api_client(_app):
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _approved_version_row(version_id: int = 1):
    """Helper: an approved PG version row."""
    return {
        "id": version_id,
        "erd_hash": "abc123" * 10 + "abcd",
        "ontology_json": {
            "node_types": [
                {
                    "name": "Customer",
                    "source_table": "customers",
                    "properties": [
                        {"name": "id", "source_column": "id", "type": "integer", "is_key": True},
                        {"name": "name", "source_column": "name", "type": "string", "is_key": False},
                    ],
                }
            ],
            "relationship_types": [],
        },
        "eval_json": None,
        "status": "approved",
        "created_at": "2026-02-25T10:00:00",
    }


def _draft_version_row(version_id: int = 1):
    """Helper: a draft PG version row."""
    row = _approved_version_row(version_id)
    row["status"] = "draft"
    return row


def _build_request_body(version_id: int = 1):
    """Helper: minimal KGBuildRequest JSON."""
    return {
        "version_id": version_id,
        "erd": {
            "tables": [
                {
                    "name": "customers",
                    "columns": [
                        {"name": "id", "data_type": "INTEGER", "nullable": False, "is_primary_key": True},
                        {"name": "name", "data_type": "VARCHAR(100)", "nullable": False, "is_primary_key": False},
                    ],
                    "primary_key": "id",
                }
            ],
            "foreign_keys": [],
        },
    }


# ════════════════════════════════════════════════════════════════════
#  POST /api/v1/kg/build
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_build_returns_202(api_client: AsyncClient):
    """#1: POST → 202, status=queued, build_job_id present."""
    with (
        patch("app.routers.kg_build.get_version", return_value=_approved_version_row()),
        patch("app.routers.kg_build.run_kg_build"),  # don't actually run
    ):
        resp = await api_client.post("/api/v1/kg/build", json=_build_request_body())
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["build_job_id"].startswith("build_")
    assert data["version_id"] == 1


@pytest.mark.anyio
async def test_build_requires_approved_version(api_client: AsyncClient):
    """#2: POST with draft version → 409."""
    with patch("app.routers.kg_build.get_version", return_value=_draft_version_row()):
        resp = await api_client.post("/api/v1/kg/build", json=_build_request_body())
    assert resp.status_code == 409
    assert "approved" in resp.json()["detail"]


@pytest.mark.anyio
async def test_build_version_not_found(api_client: AsyncClient):
    """#3: POST with non-existent version_id → 404."""
    with patch("app.routers.kg_build.get_version", return_value=None):
        resp = await api_client.post("/api/v1/kg/build", json=_build_request_body(999))
    assert resp.status_code == 404
    assert "999" in resp.json()["detail"]


# ════════════════════════════════════════════════════════════════════
#  GET /api/v1/kg/build/{job_id}
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_get_job_status_queued(api_client: AsyncClient):
    """#4: GET queued job → 200, status=queued."""
    with (
        patch("app.routers.kg_build.get_version", return_value=_approved_version_row()),
        patch("app.routers.kg_build.run_kg_build"),
    ):
        post_resp = await api_client.post("/api/v1/kg/build", json=_build_request_body())
        job_id = post_resp.json()["build_job_id"]

        resp = await api_client.get(f"/api/v1/kg/build/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


@pytest.mark.anyio
async def test_get_job_not_found(api_client: AsyncClient):
    """#5: GET /nonexistent → 404."""
    resp = await api_client.get("/api/v1/kg/build/nonexistent_job_id")
    assert resp.status_code == 404
    assert "nonexistent_job_id" in resp.json()["detail"]


# ════════════════════════════════════════════════════════════════════
#  Build execution
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_build_succeeds(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#6: Full build → status=succeeded with progress."""
    from app.kg_builder.service import create_job, run_kg_build
    from app.models.schemas import OntologySpec
    from app.ontology.fk_rule_engine import build_ontology

    ontology = build_ontology(ecommerce_erd)
    job_id = "test_build_succeed"
    create_job(job_id, 1)

    mock_stats = {"nodes": 60, "relationships": 97, "neo4j_nodes": 60, "neo4j_relationships": 97}
    with (
        patch("app.kg_builder.service.load_to_neo4j", return_value=mock_stats),
    ):
        run_kg_build(job_id, 1, ecommerce_erd, ontology)

    resp = await api_client.get(f"/api/v1/kg/build/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "succeeded"
    assert data["progress"]["nodes_created"] == 60
    assert data["progress"]["relationships_created"] == 97
    assert data["completed_at"] is not None


@pytest.mark.anyio
async def test_build_failure_records_error(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#7: Neo4j failure → status=failed with error detail."""
    from app.kg_builder.service import create_job, run_kg_build
    from app.ontology.fk_rule_engine import build_ontology

    ontology = build_ontology(ecommerce_erd)
    job_id = "test_build_fail"
    create_job(job_id, 1)

    with (
        patch(
            "app.kg_builder.service.load_to_neo4j",
            side_effect=ConnectionError("Neo4j unreachable"),
        ),
        patch("neo4j.GraphDatabase.driver"),  # don't attempt real cleanup
    ):
        run_kg_build(job_id, 1, ecommerce_erd, ontology)

    resp = await api_client.get(f"/api/v1/kg/build/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["error"]["stage"] == "neo4j_load"
    assert "Neo4j unreachable" in data["error"]["message"]


@pytest.mark.anyio
async def test_build_progress_has_counts(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#8: Succeeded build progress has nodes/rels counts."""
    from app.kg_builder.service import create_job, run_kg_build
    from app.ontology.fk_rule_engine import build_ontology

    ontology = build_ontology(ecommerce_erd)
    job_id = "test_build_counts"
    create_job(job_id, 1)

    mock_stats = {"nodes": 42, "relationships": 55, "neo4j_nodes": 42, "neo4j_relationships": 55}
    with patch("app.kg_builder.service.load_to_neo4j", return_value=mock_stats):
        run_kg_build(job_id, 1, ecommerce_erd, ontology)

    resp = await api_client.get(f"/api/v1/kg/build/{job_id}")
    data = resp.json()
    assert data["progress"]["nodes_created"] == 42
    assert data["progress"]["relationships_created"] == 55
    assert data["progress"]["duration_seconds"] >= 0


@pytest.mark.anyio
async def test_fk_integrity_verified(ecommerce_erd: ERDSchema):
    """#9: verify_fk_integrity is called during build."""
    from app.kg_builder.service import create_job, run_kg_build
    from app.ontology.fk_rule_engine import build_ontology

    ontology = build_ontology(ecommerce_erd)
    job_id = "test_fk_verify"
    create_job(job_id, 1)

    mock_stats = {"nodes": 10, "relationships": 5}
    with (
        patch("app.kg_builder.service.load_to_neo4j", return_value=mock_stats),
        patch(
            "app.kg_builder.service.verify_fk_integrity",
            return_value=[],
        ) as mock_verify,
    ):
        run_kg_build(job_id, 1, ecommerce_erd, ontology)

    mock_verify.assert_called_once()


@pytest.mark.anyio
async def test_pg_store_best_effort(api_client: AsyncClient, ecommerce_erd: ERDSchema):
    """#10: PG failure doesn't break the build."""
    from app.kg_builder.service import create_job, run_kg_build
    from app.ontology.fk_rule_engine import build_ontology

    ontology = build_ontology(ecommerce_erd)
    job_id = "test_pg_fail"
    create_job(job_id, 1)

    mock_stats = {"nodes": 10, "relationships": 5}
    with (
        patch("app.kg_builder.service.load_to_neo4j", return_value=mock_stats),
        patch(
            "app.db.kg_build_store.save_build",
            side_effect=Exception("PG down"),
        ),
        patch(
            "app.db.kg_build_store.update_build",
            side_effect=Exception("PG down"),
        ),
    ):
        run_kg_build(job_id, 1, ecommerce_erd, ontology)

    # Job should still be succeeded in memory
    resp = await api_client.get(f"/api/v1/kg/build/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"


# ════════════════════════════════════════════════════════════════════
#  Tenant isolation — failure cleanup
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_failure_cleanup_scoped_to_tenant(ecommerce_erd: ERDSchema):
    """#11: Build failure cleanup only deletes tenant-scoped labels."""
    from app.kg_builder.service import create_job, run_kg_build
    from app.ontology.fk_rule_engine import build_ontology

    ontology = build_ontology(ecommerce_erd)
    job_id = "test_tenant_cleanup"
    create_job(job_id, 1)

    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch(
            "app.kg_builder.service.load_to_neo4j",
            side_effect=ConnectionError("fail"),
        ),
        patch("app.db.neo4j_client.get_driver", return_value=mock_driver),
    ):
        run_kg_build(job_id, 1, ecommerce_erd, ontology, tenant_id="acme")

    # Should have called DELETE with prefixed labels, NOT global MATCH (n) DETACH DELETE n
    calls = [str(c) for c in mock_session.run.call_args_list]
    assert any("t_acme_" in c for c in calls), f"Expected tenant-scoped cleanup, got: {calls}"
    assert not any(
        "MATCH (n) DETACH DELETE n" in c for c in calls
    ), "Global DETACH DELETE must not be used in multi-tenant mode"


@pytest.mark.anyio
async def test_failure_cleanup_global_when_no_tenant(ecommerce_erd: ERDSchema):
    """#12: Build failure cleanup uses global delete when tenant_id is None (single-tenant)."""
    from app.kg_builder.service import create_job, run_kg_build
    from app.ontology.fk_rule_engine import build_ontology

    ontology = build_ontology(ecommerce_erd)
    job_id = "test_no_tenant_cleanup"
    create_job(job_id, 1)

    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch(
            "app.kg_builder.service.load_to_neo4j",
            side_effect=ConnectionError("fail"),
        ),
        patch("app.db.neo4j_client.get_driver", return_value=mock_driver),
    ):
        run_kg_build(job_id, 1, ecommerce_erd, ontology, tenant_id=None)

    calls = [str(c) for c in mock_session.run.call_args_list]
    assert any("MATCH (n) DETACH DELETE n" in c for c in calls)


@pytest.mark.anyio
async def test_tenant_label_prefix_none_returns_empty():
    """#13: tenant_label_prefix(None) → empty string."""
    from app.tenant import tenant_label_prefix
    assert tenant_label_prefix(None) == ""
    assert tenant_label_prefix("acme") == "t_acme_"
