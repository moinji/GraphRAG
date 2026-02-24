"""PostgreSQL client for ontology version storage."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import psycopg2
import psycopg2.extras

from app.config import settings

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ontology_versions (
    id          SERIAL PRIMARY KEY,
    erd_hash    VARCHAR(64) NOT NULL,
    ontology_json JSONB NOT NULL,
    eval_json   JSONB,
    created_at  TIMESTAMP DEFAULT NOW()
);
"""


def _get_conn():
    """Create a new PG connection."""
    return psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname=settings.postgres_db,
        connect_timeout=5,
    )


def ensure_table() -> None:
    """Create ontology_versions table if it doesn't exist."""
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TABLE_SQL)
        conn.close()
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
) -> int | None:
    """Insert a new ontology version row. Returns the version id, or None on failure."""
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ontology_versions (erd_hash, ontology_json, eval_json)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (
                        erd_hash,
                        json.dumps(ontology_json),
                        json.dumps(eval_json) if eval_json else None,
                    ),
                )
                row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        logger.warning("Failed to save ontology version", exc_info=True)
        return None


def get_version(version_id: int) -> dict[str, Any] | None:
    """Retrieve a single ontology version by id."""
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM ontology_versions WHERE id = %s",
                    (version_id,),
                )
                row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        logger.warning("Failed to get ontology version", exc_info=True)
        return None
