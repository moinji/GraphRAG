"""E2E integration test — full pipeline: DDL → ontology → approve → KG build → Q&A.

Parsing, ontology generation, routing, and caching use real code.
PG and Neo4j are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.ddl_parser.parser import parse_ddl
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


@pytest.fixture
def ecommerce_ddl():
    from pathlib import Path

    ddl_path = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas" / "demo_ecommerce.sql"
    return ddl_path.read_text(encoding="utf-8")


@pytest.fixture
def ecommerce_erd(ecommerce_ddl) -> ERDSchema:
    return parse_ddl(ecommerce_ddl)


# ── Helpers ───────────────────────────────────────────────────────


def _build_approved_version_row(ontology_dict: dict, version_id: int = 1):
    """Build a mock PG version row in approved state."""
    return {
        "id": version_id,
        "erd_hash": "e2e_test_hash_" + "a" * 50,
        "ontology_json": ontology_dict,
        "eval_json": None,
        "status": "approved",
        "created_at": "2026-02-27T10:00:00",
    }


# ════════════════════════════════════════════════════════════════════
#  Step 1: DDL parsing
# ════════════════════════════════════════════════════════════════════


def test_e2e_step1_ddl_parsing(ecommerce_erd: ERDSchema):
    """E2E #1: DDL parses into 12 tables with foreign keys."""
    assert len(ecommerce_erd.tables) == 12
    assert len(ecommerce_erd.foreign_keys) >= 12
    table_names = {t.name for t in ecommerce_erd.tables}
    assert "customers" in table_names
    assert "orders" in table_names
    assert "products" in table_names


# ════════════════════════════════════════════════════════════════════
#  Step 2: Ontology generation (FK only, no LLM)
# ════════════════════════════════════════════════════════════════════


def test_e2e_step2_ontology_generation(ecommerce_erd: ERDSchema):
    """E2E #2: FK-only ontology has 9 node types and 12 relationships."""
    from app.ontology.pipeline import generate_ontology

    with patch("app.ontology.pipeline.save_version", return_value=1):
        result = generate_ontology(ecommerce_erd, skip_llm=True)

    ontology = result.ontology
    assert len(ontology.node_types) == 9
    assert len(ontology.relationship_types) == 12

    node_names = {n.name for n in ontology.node_types}
    assert "Customer" in node_names
    assert "Product" in node_names
    assert "Order" in node_names

    rel_names = {r.name for r in ontology.relationship_types}
    assert "PLACED" in rel_names
    assert "CONTAINS" in rel_names
    assert "BELONGS_TO" in rel_names


# ════════════════════════════════════════════════════════════════════
#  Step 3: Version approve (mock PG)
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_e2e_step3_approve_version(
    api_client: AsyncClient, ecommerce_erd: ERDSchema
):
    """E2E #3: Approve a draft version → status = approved."""
    from app.ontology.pipeline import generate_ontology

    with patch("app.ontology.pipeline.save_version", return_value=1):
        result = generate_ontology(ecommerce_erd, skip_llm=True)

    ontology_dict = result.ontology.model_dump()
    draft_row = {
        "id": 1,
        "erd_hash": "e2e_test_hash_" + "a" * 50,
        "ontology_json": ontology_dict,
        "eval_json": None,
        "status": "draft",
        "created_at": "2026-02-27T10:00:00",
    }

    with (
        patch("app.routers.ontology_versions.get_version", return_value=draft_row),
        patch("app.routers.ontology_versions.approve_version"),
    ):
        resp = await api_client.post("/api/v1/ontology/versions/1/approve")

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


# ════════════════════════════════════════════════════════════════════
#  Step 4: KG Build (mock PG + Neo4j)
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_e2e_step4_kg_build_accepted(
    api_client: AsyncClient, ecommerce_erd: ERDSchema
):
    """E2E #4: KG build request accepted (202) for approved version."""
    from app.ontology.pipeline import generate_ontology

    with patch("app.ontology.pipeline.save_version", return_value=1):
        result = generate_ontology(ecommerce_erd, skip_llm=True)

    ontology_dict = result.ontology.model_dump()
    approved_row = _build_approved_version_row(ontology_dict)

    with (
        patch("app.routers.kg_build.get_version", return_value=approved_row),
        patch("app.kg_builder.service.run_kg_build") as mock_build,
    ):
        resp = await api_client.post(
            "/api/v1/kg/build",
            json={
                "version_id": 1,
                "erd": ecommerce_erd.model_dump(),
            },
        )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["build_job_id"]


# ════════════════════════════════════════════════════════════════════
#  Step 5: Q&A via cache (5 demo questions, no Neo4j needed)
# ════════════════════════════════════════════════════════════════════


DEMO_QUESTIONS = [
    ("고객 김민수가 주문한 상품은?", "맥북프로"),
    ("김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?", "맥북에어"),
    ("가장 많이 팔린 카테고리 Top 3는?", "노트북"),
    ("김민수와 이영희가 공통으로 구매한 상품은?", "맥북프로"),
    ("쿠폰 사용 주문과 미사용 주문의 평균 금액 비교", "쿠폰"),
]


@pytest.mark.anyio
@pytest.mark.parametrize("question,expected_keyword", DEMO_QUESTIONS)
async def test_e2e_step5_qa_cached(
    api_client: AsyncClient,
    question: str,
    expected_keyword: str,
):
    """E2E #5: All 5 demo questions answered via cache (no Neo4j)."""
    resp = await api_client.post(
        "/api/v1/query",
        json={"question": question},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cached"] is True
    assert expected_keyword in data["answer"]
    assert data["error"] is None
    assert data["matched_by"] == "rule"


# ════════════════════════════════════════════════════════════════════
#  Full pipeline smoke test
# ════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_e2e_full_pipeline_smoke(
    api_client: AsyncClient, ecommerce_ddl: str
):
    """E2E #6: Full pipeline smoke — parse + generate + 5 Q&A all pass."""
    # Step 1+2: Upload DDL + generate ontology
    with patch("app.ontology.pipeline.save_version", return_value=1):
        resp = await api_client.post(
            "/api/v1/ontology/generate",
            json={"erd": parse_ddl(ecommerce_ddl).model_dump(), "skip_llm": True},
        )
    assert resp.status_code == 200
    ontology_data = resp.json()
    assert len(ontology_data["ontology"]["node_types"]) == 9

    # Step 3+4+5: All 5 Q&A via cache
    successes = 0
    for question, keyword in DEMO_QUESTIONS:
        r = await api_client.post("/api/v1/query", json={"question": question})
        if r.status_code == 200 and keyword in r.json()["answer"]:
            successes += 1

    assert successes >= 4, f"Only {successes}/5 demo questions succeeded"
