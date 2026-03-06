"""PostgreSQL client for ontology version storage."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool

from app.config import settings

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ontology_versions (
    id          SERIAL PRIMARY KEY,
    erd_hash    VARCHAR(64) NOT NULL,
    ontology_json JSONB NOT NULL,
    eval_json   JSONB,
    status      VARCHAR(20) DEFAULT 'draft' NOT NULL,
    tenant_id   VARCHAR(64) DEFAULT '_default_' NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);
"""

# Connection pool (lazy-initialized)
_pool: psycopg2.pool.SimpleConnectionPool | None = None


def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            dbname=settings.postgres_db,
            connect_timeout=5,
        )
    return _pool


@contextmanager
def _get_conn():
    """Get a PG connection from the pool (auto-returned on exit)."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


def close_pool() -> None:
    """Close all pool connections (call on shutdown)."""
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.closeall()
        _pool = None


def ensure_table() -> None:
    """Create ontology_versions table if it doesn't exist."""
    try:
        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_TABLE_SQL)
        logger.info("ontology_versions table ensured")
    except Exception:
        logger.warning("Failed to ensure ontology_versions table", exc_info=True)


def compute_erd_hash(erd_dict: dict) -> str:
    """Compute a deterministic SHA-256 hash of an ERD dict."""
    canonical = json.dumps(erd_dict, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_version(
    erd_hash: str,
    ontology_json: dict[str, Any],
    eval_json: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> int | None:
    """Insert a new ontology version row. Returns the version id, or None on failure."""
    from app.tenant import tenant_db_id
    tid = tenant_db_id(tenant_id)
    try:
        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO ontology_versions (erd_hash, ontology_json, eval_json, tenant_id)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            erd_hash,
                            json.dumps(ontology_json),
                            json.dumps(eval_json) if eval_json else None,
                            tid,
                        ),
                    )
                    row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        logger.warning("Failed to save ontology version", exc_info=True)
        return None


def get_version(version_id: int, tenant_id: str | None = None) -> dict[str, Any] | None:
    """Retrieve a single ontology version by id (tenant-scoped)."""
    from app.tenant import tenant_db_id
    tid = tenant_db_id(tenant_id)
    try:
        with _get_conn() as conn:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT * FROM ontology_versions WHERE id = %s AND tenant_id = %s",
                        (version_id, tid),
                    )
                    row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        logger.warning("Failed to get ontology version", exc_info=True)
        return None


def update_version(
    version_id: int,
    ontology_json: dict[str, Any],
    eval_json: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> bool:
    """Update ontology and eval for a draft version. Returns True on success."""
    from app.tenant import tenant_db_id
    tid = tenant_db_id(tenant_id)
    try:
        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE ontology_versions
                        SET ontology_json = %s, eval_json = %s
                        WHERE id = %s AND status = 'draft' AND tenant_id = %s
                        """,
                        (
                            json.dumps(ontology_json),
                            json.dumps(eval_json) if eval_json else None,
                            version_id,
                            tid,
                        ),
                    )
                    updated = cur.rowcount > 0
        return updated
    except Exception:
        logger.warning("Failed to update ontology version", exc_info=True)
        return False


def approve_version(version_id: int, tenant_id: str | None = None) -> bool:
    """Set version status to 'approved'. Returns True on success."""
    from app.tenant import tenant_db_id
    tid = tenant_db_id(tenant_id)
    try:
        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE ontology_versions
                        SET status = 'approved'
                        WHERE id = %s AND status = 'draft' AND tenant_id = %s
                        """,
                        (version_id, tid),
                    )
                    updated = cur.rowcount > 0
        return updated
    except Exception:
        logger.warning("Failed to approve ontology version", exc_info=True)
        return False
