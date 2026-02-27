"""KG Build service — orchestrates data generation + Neo4j loading.

Uses in-memory dict as primary job store with PG as best-effort backup.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.config import settings
from app.data_generator.generator import generate_sample_data, verify_fk_integrity
from app.kg_builder.loader import load_to_neo4j
from app.models.schemas import (
    ERDSchema,
    KGBuildErrorDetail,
    KGBuildProgress,
    KGBuildResponse,
    OntologySpec,
)

logger = logging.getLogger(__name__)

# In-memory job store — primary source of truth for polling
_jobs: dict[str, KGBuildResponse] = {}


def get_job(job_id: str) -> KGBuildResponse | None:
    """Get job status from in-memory store."""
    return _jobs.get(job_id)


def create_job(job_id: str, version_id: int) -> KGBuildResponse:
    """Create a new queued job in memory and PG (best-effort)."""
    job = KGBuildResponse(
        build_job_id=job_id,
        status="queued",
        version_id=version_id,
    )
    _jobs[job_id] = job

    # PG best-effort
    try:
        from app.db.kg_build_store import save_build

        save_build(job_id, version_id)
    except Exception:
        logger.warning("PG save_build failed for %s", job_id, exc_info=True)

    return job


def run_kg_build(
    job_id: str,
    version_id: int,
    erd: ERDSchema,
    ontology: OntologySpec,
    csv_data: dict[str, list[dict]] | None = None,
) -> None:
    """Execute the full KG build pipeline (runs in background task).

    Steps:
    1. Update status → running
    2. Generate sample data (or use CSV data) + verify FK integrity
    3. Load to Neo4j
    4. On success: status → succeeded with progress counts
    5. On failure: status → failed with error detail, clean partial graph
    """
    started = datetime.now(timezone.utc)
    started_str = started.isoformat()
    start_time = time.monotonic()

    # 1. Mark running
    _update_job(job_id, status="running", started_at=started_str)

    try:
        # 2. Use CSV data if provided, otherwise generate sample data
        data = csv_data if csv_data is not None else generate_sample_data(erd)
        violations = verify_fk_integrity(data, erd)
        if violations:
            logger.warning("FK integrity violations: %s", violations)

        # 3. Load to Neo4j
        stats = load_to_neo4j(
            ontology,
            data,
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )

        # 4. Success
        duration = time.monotonic() - start_time
        completed_str = datetime.now(timezone.utc).isoformat()
        progress = KGBuildProgress(
            nodes_created=stats.get("nodes", 0),
            relationships_created=stats.get("relationships", 0),
            duration_seconds=round(duration, 1),
        )
        _update_job(
            job_id,
            status="succeeded",
            progress=progress,
            completed_at=completed_str,
        )

    except Exception as exc:
        # 5. Failure — determine stage
        duration = time.monotonic() - start_time
        completed_str = datetime.now(timezone.utc).isoformat()
        stage = "neo4j_load" if "data" in dir() else "data_generation"
        error_detail = KGBuildErrorDetail(
            stage=stage,
            message=str(exc),
        )
        _update_job(
            job_id,
            status="failed",
            error=error_detail,
            completed_at=completed_str,
        )

        # Clean partial graph (best-effort)
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            with driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
            driver.close()
        except Exception:
            logger.warning("Failed to clean partial graph", exc_info=True)

        logger.error("KG build %s failed: %s", job_id, exc, exc_info=True)


def _update_job(
    job_id: str,
    status: str,
    progress: KGBuildProgress | None = None,
    error: KGBuildErrorDetail | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    """Update job in memory and PG (best-effort)."""
    job = _jobs.get(job_id)
    if job:
        _jobs[job_id] = job.model_copy(
            update={
                "status": status,
                **({"progress": progress} if progress is not None else {}),
                **({"error": error} if error is not None else {}),
                **({"started_at": started_at} if started_at is not None else {}),
                **({"completed_at": completed_at} if completed_at is not None else {}),
            }
        )

    # PG best-effort
    try:
        from app.db.kg_build_store import update_build

        update_build(
            job_id,
            status=status,
            progress=progress.model_dump() if progress else None,
            error=error.model_dump() if error else None,
            started_at=started_at,
            completed_at=completed_at,
        )
    except Exception:
        logger.warning("PG update_build failed for %s", job_id, exc_info=True)
