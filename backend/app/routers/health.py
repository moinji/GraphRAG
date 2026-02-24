"""Health check endpoint."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/v1", tags=["health"])


def _check_neo4j() -> dict[str, Any]:
    try:
        from neo4j import GraphDatabase

        t0 = time.perf_counter()
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        driver.verify_connectivity()
        latency = round((time.perf_counter() - t0) * 1000, 1)
        driver.close()
        return {"status": "ok", "latency_ms": latency}
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


def _check_redis() -> dict[str, Any]:
    try:
        import redis as redis_lib

        t0 = time.perf_counter()
        r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=3)
        r.ping()
        latency = round((time.perf_counter() - t0) * 1000, 1)
        r.close()
        return {"status": "ok", "latency_ms": latency}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/health")
def health_check() -> dict[str, Any]:
    neo4j = _check_neo4j()
    postgres = _check_postgres()
    redis = _check_redis()

    all_ok = all(s["status"] == "ok" for s in [neo4j, postgres, redis])
    return {
        "status": "healthy" if all_ok else "degraded",
        "neo4j": neo4j,
        "postgres": postgres,
        "redis": redis,
    }
