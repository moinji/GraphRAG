"""PostgreSQL CRUD for kg_builds table (best-effort)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS kg_builds (
    id           VARCHAR(64) PRIMARY KEY,
    version_id   INTEGER NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress     JSONB,
    error        JSONB,
    started_at   TIMESTAMP,
    completed_at TIMESTAMP,
    created_at   TIMESTAMP DEFAULT NOW()
);
"""


def ensure_kg_builds_table() -> None:
    """Create kg_builds table if it doesn't exist."""
    try:
        from app.db.pg_client import _get_conn

        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TABLE_SQL)
        conn.close()
        logger.info("kg_builds table ensured")
    except Exception:
        logger.warning("Failed to ensure kg_builds table", exc_info=True)


def save_build(job_id: str, version_id: int) -> None:
    """Insert a new build job row (status=queued)."""
    try:
        from app.db.pg_client import _get_conn

        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kg_builds (id, version_id, status)
                    VALUES (%s, %s, 'queued')
                    """,
                    (job_id, version_id),
                )
        conn.close()
    except Exception:
        logger.warning("Failed to save build job %s", job_id, exc_info=True)


def update_build(
    job_id: str,
    status: str,
    progress: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    """Update an existing build job row."""
    try:
        from app.db.pg_client import _get_conn

        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE kg_builds
                    SET status = %s,
                        progress = %s,
                        error = %s,
                        started_at = %s,
                        completed_at = %s
                    WHERE id = %s
                    """,
                    (
                        status,
                        json.dumps(progress) if progress else None,
                        json.dumps(error) if error else None,
                        started_at,
                        completed_at,
                        job_id,
                    ),
                )
        conn.close()
    except Exception:
        logger.warning("Failed to update build job %s", job_id, exc_info=True)


def get_build(job_id: str) -> dict[str, Any] | None:
    """Retrieve a build job by id."""
    try:
        import psycopg2.extras

        from app.db.pg_client import _get_conn

        conn = _get_conn()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM kg_builds WHERE id = %s", (job_id,))
                row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        logger.warning("Failed to get build job %s", job_id, exc_info=True)
        return None
