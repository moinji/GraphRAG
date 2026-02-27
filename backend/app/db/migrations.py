"""PG schema migrations — idempotent, run at startup."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MIGRATIONS = [
    # Week 3: add status column for draft/approved workflow
    """
    ALTER TABLE ontology_versions
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'draft' NOT NULL;
    """,
]


def run_migrations() -> None:
    """Apply all pending migrations (idempotent)."""
    try:
        from app.db.pg_client import _get_conn

        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                for sql in _MIGRATIONS:
                    cur.execute(sql)
        conn.close()
        logger.info("Migrations applied successfully")
    except Exception:
        logger.warning("Failed to run migrations", exc_info=True)

    # Week 4: ensure kg_builds table
    try:
        from app.db.kg_build_store import ensure_kg_builds_table

        ensure_kg_builds_table()
    except Exception:
        logger.warning("Failed to ensure kg_builds table", exc_info=True)
