"""Migration job orchestrator — same pattern as kg_builder/service.py."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.config import settings
from app.data_generator.generator import generate_sample_data, verify_fk_integrity
from app.models.schemas import (
    ERDSchema,
    KGBuildErrorDetail,
    MigrationProgress,
    MigrationResponse,
    OntologyDiff,
    OntologySpec,
)
from app.schema_evolution.diff import compute_diff
from app.schema_evolution.migrator import run_incremental_migration

logger = logging.getLogger(__name__)

_jobs: dict[str, MigrationResponse] = {}


def get_migration_job(job_id: str) -> MigrationResponse | None:
    return _jobs.get(job_id)


def create_migration_job(
    job_id: str,
    base_version_id: int,
    target_version_id: int,
) -> MigrationResponse:
    job = MigrationResponse(
        migration_job_id=job_id,
        status="queued",
        base_version_id=base_version_id,
        target_version_id=target_version_id,
    )
    _jobs[job_id] = job
    return job


def run_migration(
    job_id: str,
    base_ontology: OntologySpec,
    target_ontology: OntologySpec,
    base_version_id: int,
    target_version_id: int,
    erd: ERDSchema,
    csv_data: dict[str, list[dict]] | None = None,
    tenant_id: str | None = None,
    dry_run: bool = False,
) -> None:
    """Execute full migration pipeline (runs in background task)."""
    started = datetime.now(timezone.utc)
    started_str = started.isoformat()
    start_time = time.monotonic()

    _update_job(job_id, status="running", started_at=started_str)

    try:
        # 1. Compute diff
        _update_job(job_id, status="running", progress=MigrationProgress(
            current_step="computing_diff", step_number=0, total_steps=6,
        ))
        diff = compute_diff(base_ontology, target_ontology, base_version_id, target_version_id)
        _update_job(job_id, diff=diff)

        if not diff.node_diffs and not diff.relationship_diffs:
            _update_job(
                job_id, status="succeeded",
                progress=MigrationProgress(current_step="no_changes", step_number=6, total_steps=6),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            return

        # 2. Impact analysis (best-effort)
        try:
            from app.schema_evolution.impact import analyze_impact
            impact = analyze_impact(diff, base_ontology, target_ontology, tenant_id)
            _update_job(job_id, impact=impact)
        except Exception:
            logger.warning("Impact analysis failed — continuing migration", exc_info=True)

        # 3. Dry run — stop here
        if dry_run:
            _update_job(
                job_id, status="succeeded",
                progress=MigrationProgress(current_step="dry_run_complete", step_number=6, total_steps=6),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            return

        # 4. Prepare data for new nodes/relationships
        data = csv_data if csv_data is not None else generate_sample_data(erd)

        # 5. Run incremental migration
        def progress_cb(p: MigrationProgress):
            _update_job(job_id, progress=p)

        stats = run_incremental_migration(
            diff, base_ontology, target_ontology, data,
            tenant_id=tenant_id, progress_callback=progress_cb,
        )

        # 6. Invalidate caches
        _invalidate_caches(tenant_id)

        # 7. Success
        duration = time.monotonic() - start_time
        progress = MigrationProgress(
            current_step="completed",
            step_number=6,
            total_steps=6,
            nodes_added=stats.get("nodes_added", 0),
            nodes_removed=stats.get("nodes_removed", 0),
            relationships_added=stats.get("relationships_added", 0),
            relationships_removed=stats.get("relationships_removed", 0),
            properties_modified=stats.get("properties_modified", 0),
            duration_seconds=round(duration, 1),
        )
        _update_job(
            job_id, status="succeeded",
            progress=progress,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as exc:
        duration = time.monotonic() - start_time
        error = KGBuildErrorDetail(stage="migration", message=str(exc))
        _update_job(
            job_id, status="failed", error=error,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.error("Migration %s failed: %s", job_id, exc, exc_info=True)


def _invalidate_caches(tenant_id: str | None) -> None:
    for mod_path, fn_name in [
        ("app.query.local_search", "invalidate_entity_cache"),
        ("app.db.graph_schema", "invalidate_schema_cache"),
        ("app.query.pipeline", "invalidate_query_cache"),
    ]:
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            getattr(mod, fn_name)(tenant_id)
        except Exception:
            pass


def _update_job(
    job_id: str,
    status: str | None = None,
    progress: MigrationProgress | None = None,
    error: KGBuildErrorDetail | None = None,
    diff: OntologyDiff | None = None,
    impact=None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    job = _jobs.get(job_id)
    if not job:
        return
    update: dict = {}
    if status is not None:
        update["status"] = status
    if progress is not None:
        update["progress"] = progress
    if error is not None:
        update["error"] = error
    if diff is not None:
        update["diff"] = diff
    if impact is not None:
        update["impact"] = impact
    if started_at is not None:
        update["started_at"] = started_at
    if completed_at is not None:
        update["completed_at"] = completed_at
    _jobs[job_id] = job.model_copy(update=update)
