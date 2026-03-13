"""Health check endpoint."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.models.schemas import HealthCheckResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


def _check_neo4j() -> dict[str, Any]:
    try:
        from neo4j.exceptions import ServiceUnavailable

        from app.db.neo4j_client import get_driver

        t0 = time.perf_counter()
        driver = get_driver()
        driver.verify_connectivity()
        latency = round((time.perf_counter() - t0) * 1000, 1)
        return {"status": "ok", "latency_ms": latency}
    except ServiceUnavailable as e:
        detail = str(e)
        if settings.neo4j_uri.startswith("neo4j+s://"):
            detail += " — AuraDB instance may be paused or resuming. Check console.neo4j.io"
        return {"status": "error", "detail": detail}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_postgres() -> dict[str, Any]:
    try:
        import psycopg2

        t0 = time.perf_counter()
        conn = psycopg2.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            dbname=settings.postgres_db,
            connect_timeout=3,
        )
        conn.cursor().execute("SELECT 1")
        latency = round((time.perf_counter() - t0) * 1000, 1)
        conn.close()
        return {"status": "ok", "latency_ms": latency}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_llm() -> dict[str, Any]:
    from app.llm.provider import has_any_api_key

    if not has_any_api_key():
        return {"status": "error", "detail": "No API key configured"}
    providers: list[str] = []
    if settings.openai_api_key:
        providers.append(f"openai ({settings.openai_model})")
    if settings.anthropic_api_key:
        providers.append(f"anthropic ({settings.anthropic_model})")
    return {"status": "ok", "detail": ", ".join(providers)}


@router.get("/health", response_model=HealthCheckResponse)
def health_check() -> dict[str, Any]:
    from app.circuit_breaker import neo4j_breaker, pg_breaker

    neo4j = _check_neo4j()
    postgres = _check_postgres()
    llm = _check_llm()

    # Inject circuit breaker state into service health
    neo4j["circuit_breaker"] = neo4j_breaker.state.value
    postgres["circuit_breaker"] = pg_breaker.state.value

    core_ok = all(s["status"] == "ok" for s in [neo4j, postgres])
    return {
        "status": "healthy" if core_ok else "degraded",
        "neo4j": neo4j,
        "postgres": postgres,
        "llm": llm,
    }


@router.get("/llm-usage")
def llm_usage() -> dict[str, Any]:
    """Return aggregated LLM token usage and estimated costs."""
    from app.llm_tracker import tracker
    return tracker.get_summary()


@router.delete("/llm-usage")
def reset_llm_usage() -> dict[str, str]:
    """Reset LLM usage counters."""
    from app.llm_tracker import tracker
    tracker.reset()
    return {"status": "reset"}
