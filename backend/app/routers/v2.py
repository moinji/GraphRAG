"""API v2 — streamlined endpoints with consistent naming.

Changes from v1:
- GET /api/v2/status → unified health + circuit breaker + job stats
- POST /api/v2/query → same as v1 but with structured error responses
- GET /api/v2/graph/stats → same as v1 graph stats
- GET /api/v2/version → API version info

v2 endpoints delegate to existing v1 logic for consistency.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api_version import API_LATEST, API_V1, API_V2

router = APIRouter(prefix="/api/v2", tags=["v2"])


@router.get("/version")
def api_version() -> dict[str, Any]:
    """Return API version information."""
    return {
        "current": API_V2,
        "supported": [API_V1, API_V2],
        "latest": API_LATEST,
        "deprecations": [],
    }


@router.get("/status")
def unified_status(request: Request) -> dict[str, Any]:
    """Unified status: health + circuit breakers + job stats."""
    from app.circuit_breaker import neo4j_breaker, pg_breaker
    from app.job_manager import job_manager
    from app.routers.health import _check_llm, _check_neo4j, _check_postgres

    neo4j = _check_neo4j()
    postgres = _check_postgres()
    llm = _check_llm()

    core_ok = all(s["status"] == "ok" for s in [neo4j, postgres])

    return {
        "status": "healthy" if core_ok else "degraded",
        "services": {
            "neo4j": {**neo4j, "circuit_breaker": neo4j_breaker.get_status()},
            "postgres": {**postgres, "circuit_breaker": pg_breaker.get_status()},
            "llm": llm,
        },
        "jobs": job_manager.get_stats(),
    }


@router.post("/query")
def query_v2(request: Request) -> dict[str, Any]:
    """v2 query — delegates to v1 pipeline with structured response."""
    # Delegate to v1 — imported inline to avoid circular deps
    import json

    from app.models.schemas import QueryRequest
    from app.query.pipeline import run_query
    from app.tenant import get_tenant_id

    # Parse body (sync endpoint)
    import asyncio

    async def _read_body():
        return await request.body()

    loop = asyncio.new_event_loop()
    try:
        body = loop.run_until_complete(_read_body())
    finally:
        loop.close()

    data = json.loads(body)
    req = QueryRequest(**data)
    tenant_id = get_tenant_id(request)

    response = run_query(req.question, mode=req.mode, tenant_id=tenant_id)
    return {
        "version": API_V2,
        "data": response.model_dump(),
    }


@router.get("/graph/stats")
def graph_stats_v2(request: Request) -> dict[str, Any]:
    """v2 graph stats — delegates to v1 graph_stats endpoint."""
    from app.routers.graph import graph_stats

    stats = graph_stats(request)
    return {
        "version": API_V2,
        "data": stats.model_dump() if hasattr(stats, "model_dump") else stats,
    }
