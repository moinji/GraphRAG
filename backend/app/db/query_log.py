"""Query history storage — logs queries to PostgreSQL for analytics.

Best-effort: failures are logged but do not affect query execution.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS query_log (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(64) DEFAULT '_default_' NOT NULL,
    question    TEXT NOT NULL,
    mode        VARCHAR(10) NOT NULL DEFAULT 'a',
    answer      TEXT,
    template_id VARCHAR(64),
    route       VARCHAR(64),
    matched_by  VARCHAR(20),
    cached      BOOLEAN DEFAULT FALSE,
    latency_ms  INTEGER,
    error       TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_query_log_tenant_created
    ON query_log (tenant_id, created_at DESC);
"""


def ensure_query_log_table() -> None:
    """Create query_log table if it doesn't exist."""
    try:
        from app.db.pg_client import _get_conn

        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_TABLE_SQL)
                    cur.execute(_CREATE_INDEX_SQL)
        logger.info("query_log table ensured")
    except Exception:
        logger.warning("Failed to create query_log table", exc_info=True)


def log_query(
    tenant_id: str | None,
    question: str,
    mode: str,
    answer: str | None = None,
    template_id: str | None = None,
    route: str | None = None,
    matched_by: str | None = None,
    cached: bool = False,
    latency_ms: int | None = None,
    error: str | None = None,
) -> None:
    """Insert a query log entry (best-effort, non-blocking)."""
    try:
        from app.db.pg_client import _get_conn
        from app.tenant import tenant_db_id

        tid = tenant_db_id(tenant_id)
        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO query_log
                           (tenant_id, question, mode, answer, template_id,
                            route, matched_by, cached, latency_ms, error)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (tid, question, mode, answer, template_id,
                         route, matched_by, cached, latency_ms, error),
                    )
    except Exception:
        logger.debug("Failed to log query", exc_info=True)


def get_query_history(
    tenant_id: str | None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Retrieve recent query history for a tenant."""
    try:
        from app.db.pg_client import _get_conn
        from app.tenant import tenant_db_id

        tid = tenant_db_id(tenant_id)
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, question, mode, answer, template_id, route,
                              matched_by, cached, latency_ms, error, created_at
                       FROM query_log
                       WHERE tenant_id = %s
                       ORDER BY created_at DESC
                       LIMIT %s OFFSET %s""",
                    (tid, limit, offset),
                )
                cols = [d[0] for d in cur.description]
                return [
                    {c: (str(v) if c == "created_at" else v) for c, v in zip(cols, row)}
                    for row in cur.fetchall()
                ]
    except Exception:
        logger.debug("Failed to fetch query history", exc_info=True)
        return []


def get_query_analytics(tenant_id: str | None) -> dict[str, Any]:
    """Return aggregated query analytics for a tenant."""
    try:
        from app.db.pg_client import _get_conn
        from app.tenant import tenant_db_id

        tid = tenant_db_id(tenant_id)
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Total queries + cache hit rate
                cur.execute(
                    """SELECT
                         COUNT(*) AS total,
                         SUM(CASE WHEN cached THEN 1 ELSE 0 END) AS cache_hits,
                         AVG(latency_ms) AS avg_latency,
                         PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency,
                         SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS errors
                       FROM query_log
                       WHERE tenant_id = %s""",
                    (tid,),
                )
                row = cur.fetchone()
                total = row[0] or 0
                cache_hits = row[1] or 0
                avg_latency = round(row[2], 1) if row[2] else 0
                p95_latency = round(row[3], 1) if row[3] else 0
                errors = row[4] or 0

                # By mode
                cur.execute(
                    """SELECT mode, COUNT(*) AS cnt
                       FROM query_log
                       WHERE tenant_id = %s
                       GROUP BY mode ORDER BY cnt DESC""",
                    (tid,),
                )
                by_mode = {r[0]: r[1] for r in cur.fetchall()}

                # By route
                cur.execute(
                    """SELECT route, COUNT(*) AS cnt
                       FROM query_log
                       WHERE tenant_id = %s AND route IS NOT NULL
                       GROUP BY route ORDER BY cnt DESC""",
                    (tid,),
                )
                by_route = {r[0]: r[1] for r in cur.fetchall()}

                return {
                    "total_queries": total,
                    "cache_hit_rate": round(cache_hits / total, 3) if total > 0 else 0,
                    "avg_latency_ms": avg_latency,
                    "p95_latency_ms": p95_latency,
                    "error_count": errors,
                    "error_rate": round(errors / total, 3) if total > 0 else 0,
                    "by_mode": by_mode,
                    "by_route": by_route,
                }
    except Exception:
        logger.debug("Failed to compute query analytics", exc_info=True)
        return {"total_queries": 0, "error": "Analytics unavailable"}
