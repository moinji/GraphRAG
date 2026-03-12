"""KG Build service — orchestrates data generation + Neo4j loading.

PG is the primary job store; in-memory dict serves as a fast cache.
If PG is unavailable, falls back to in-memory only (graceful degradation).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.config import settings
from app.data_generator.generator import generate_sample_data, verify_fk_integrity
from app.kg_builder.loader import load_from_mapping, load_to_neo4j
from app.models.schemas import (
    ERDSchema,
    KGBuildErrorDetail,
    KGBuildProgress,
    KGBuildResponse,
    OntologySpec,
)

logger = logging.getLogger(__name__)

# In-memory job cache — fast lookup, PG is authoritative
MAX_COMPLETED_JOBS = 100
_jobs: dict[str, KGBuildResponse] = {}
_active_builds: set[str] = set()  # job IDs currently running
SHUTDOWN_WAIT_MAX = 30  # max seconds to wait for active builds on shutdown


def wait_for_active_builds() -> None:
    """Block until all active KG builds finish, up to SHUTDOWN_WAIT_MAX seconds."""
    if not _active_builds:
        return
    logger.info("Waiting for %d active KG build(s) to finish...", len(_active_builds))
    deadline = time.monotonic() + SHUTDOWN_WAIT_MAX
    while _active_builds and time.monotonic() < deadline:
        time.sleep(0.5)
    if _active_builds:
        logger.warning("Shutdown timeout: %d build(s) still active", len(_active_builds))
    else:
        logger.info("All active KG builds finished.")


def _prune_completed_jobs() -> None:
    """Remove oldest completed/failed jobs when exceeding MAX_COMPLETED_JOBS."""
    terminal = [
        (jid, job) for jid, job in _jobs.items()
        if job.status in ("succeeded", "failed")
    ]
    if len(terminal) <= MAX_COMPLETED_JOBS:
        return
    # Sort by completed_at (oldest first), prune excess
    terminal.sort(key=lambda x: x[1].completed_at or "")
    excess = len(terminal) - MAX_COMPLETED_JOBS
    for jid, _ in terminal[:excess]:
        del _jobs[jid]


def get_job(job_id: str, tenant_id: str | None = None) -> KGBuildResponse | None:
    """Get job status from cache, falling back to PG (authoritative)."""
    job = _jobs.get(job_id)
    if job is not None:
        return job

    # Fallback: try PG (handles server restart)
    try:
        from app.db.kg_build_store import get_build

        row = get_build(job_id, tenant_id=tenant_id)
        if row is None:
            return None
        job = KGBuildResponse(
            build_job_id=row["id"],
            status=row["status"],
            version_id=row["version_id"],
            progress=KGBuildProgress(**(row["progress"] or {})) if row.get("progress") else None,
            error=KGBuildErrorDetail(**(row["error"] or {})) if row.get("error") else None,
            started_at=row.get("started_at", "").isoformat() if row.get("started_at") else None,
            completed_at=row.get("completed_at", "").isoformat() if row.get("completed_at") else None,
        )
        _jobs[job_id] = job  # re-cache
        return job
    except Exception:
        logger.warning("PG fallback failed for job %s", job_id, exc_info=True)
        return None


def create_job(job_id: str, version_id: int, tenant_id: str | None = None) -> KGBuildResponse:
    """Create a new queued job — PG primary, in-memory cache."""
    _prune_completed_jobs()
    job = KGBuildResponse(
        build_job_id=job_id,
        status="queued",
        version_id=version_id,
    )

    # PG primary
    try:
        from app.db.kg_build_store import save_build

        save_build(job_id, version_id, tenant_id=tenant_id)
    except Exception:
        logger.warning("PG save_build failed for %s — using in-memory only", job_id, exc_info=True)

    # Cache in memory
    _jobs[job_id] = job
    return job


def run_kg_build(
    job_id: str,
    version_id: int,
    erd: ERDSchema,
    ontology: OntologySpec,
    csv_data: dict[str, list[dict]] | None = None,
    tenant_id: str | None = None,
    mapping_config: "DomainMappingConfig | None" = None,
) -> None:
    """Execute the full KG build pipeline (runs in background task).

    Steps:
    1. Update status → running
    2. Generate sample data (or use CSV data) + verify FK integrity
    3. Load to Neo4j
    4. On success: status → succeeded with progress counts
    5. On failure: status → failed with error detail, clean partial graph
    """
    _active_builds.add(job_id)
    started = datetime.now(timezone.utc)
    started_str = started.isoformat()
    start_time = time.monotonic()

    # 1. Mark running
    _update_job(
        job_id,
        status="running",
        started_at=started_str,
        progress=KGBuildProgress(current_step="starting", step_number=0, total_steps=4),
    )

    try:
        # 2. Data generation / CSV
        _update_job(
            job_id, status="running",
            progress=KGBuildProgress(current_step="data_generation", step_number=1, total_steps=4),
        )
        data = csv_data if csv_data is not None else generate_sample_data(erd)

        # 3. FK integrity verification
        _update_job(
            job_id, status="running",
            progress=KGBuildProgress(current_step="fk_verification", step_number=2, total_steps=4),
        )
        violations = verify_fk_integrity(data, erd)
        fk_error_count = len(violations) if violations else 0
        if violations:
            logger.warning("FK integrity violations: %s", violations)

        # 4. Load to Neo4j
        _update_job(
            job_id, status="running",
            progress=KGBuildProgress(current_step="neo4j_load", step_number=3, total_steps=4),
        )
        if mapping_config is not None:
            stats = load_from_mapping(
                mapping_config,
                data,
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password,
                tenant_id=tenant_id,
            )
        else:
            stats = load_to_neo4j(
                ontology,
                data,
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password,
                tenant_id=tenant_id,
            )

        # 5. Invalidate caches after successful build
        try:
            from app.query.local_search import invalidate_entity_cache
            invalidate_entity_cache(tenant_id)
        except Exception:
            pass
        try:
            from app.db.graph_schema import invalidate_schema_cache
            invalidate_schema_cache(tenant_id)
        except Exception:
            pass
        try:
            from app.query.pipeline import invalidate_query_cache
            invalidate_query_cache(tenant_id)
        except Exception:
            pass

        # 5.5. OWL Materialization (best-effort)
        if settings.enable_owl:
            try:
                from app.db.neo4j_client import get_driver
                from app.owl.materializer import materialize_transitive, materialize_chain_fallback
                from app.owl.axiom_registry import get_axioms
                from app.owl.converter import ontology_to_owl
                from app.owl.reasoner import run_reasoning

                _driver = get_driver()
                mat_results = materialize_transitive(ontology, driver=_driver, tenant_id=tenant_id)
                mat_total = sum(mat_results.values())

                # propertyChain fallback
                detected_domain = None
                try:
                    from app.ontology.domain_hints import detect_domain
                    dh = detect_domain(erd)
                    detected_domain = dh.name if dh else None
                except Exception:
                    pass

                if detected_domain:
                    owl_g = ontology_to_owl(ontology, domain=detected_domain)
                    owl_result = run_reasoning(owl_g, domain=detected_domain)
                    if owl_result.chain_fallback_used:
                        chain_axioms = [a for a in get_axioms(detected_domain) if a.axiom_type == "propertyChain"]
                        chain_results = materialize_chain_fallback(_driver, chain_axioms, tenant_id)
                        mat_total += sum(chain_results.values())

                # stats에 물리화된 관계 수 반영
                stats["relationships"] = stats.get("relationships", 0) + mat_total

                if mat_total > 0:
                    logger.info("OWL materialization: %d closure/chain edges created", mat_total)
            except Exception:
                logger.warning("OWL materialization failed — non-fatal", exc_info=True)

        # 6. Success
        duration = time.monotonic() - start_time
        completed_str = datetime.now(timezone.utc).isoformat()
        progress = KGBuildProgress(
            nodes_created=stats.get("nodes", 0),
            relationships_created=stats.get("relationships", 0),
            duration_seconds=round(duration, 1),
            current_step="completed",
            step_number=4,
            total_steps=4,
            error_count=fk_error_count,
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

        # Clean partial graph (best-effort, tenant-scoped)
        try:
            from app.db.neo4j_client import get_driver
            from app.tenant import prefixed_label, tenant_label_prefix

            driver = get_driver()
            with driver.session() as session:
                prefix = tenant_label_prefix(tenant_id)
                if prefix:
                    for nt in ontology.node_types:
                        lbl = prefixed_label(tenant_id, nt.name)
                        session.run(f"MATCH (n:`{lbl}`) DETACH DELETE n")
                else:
                    session.run("MATCH (n) DETACH DELETE n")
        except Exception:
            logger.warning("Failed to clean partial graph", exc_info=True)

        logger.error("KG build %s failed: %s", job_id, exc, exc_info=True)

    finally:
        _active_builds.discard(job_id)


def _update_job(
    job_id: str,
    status: str,
    progress: KGBuildProgress | None = None,
    error: KGBuildErrorDetail | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    """Update job — PG primary, then sync in-memory cache."""
    # PG primary
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
        logger.warning("PG update_build failed for %s — cache-only update", job_id, exc_info=True)

    # Update in-memory cache
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
