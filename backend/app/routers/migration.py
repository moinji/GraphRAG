"""Schema evolution API — diff, impact analysis, incremental migration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks

from app.exceptions import MigrationNotFoundError, VersionNotFoundError
from app.models.schemas import (
    MigrationRequest,
    MigrationResponse,
    OntologyDiff,
    OntologySpec,
)

router = APIRouter(prefix="/api/v1", tags=["migration"])


class DiffRequest:
    """Body for diff/impact endpoints."""

    def __init__(self, base_version_id: int, target_version_id: int):
        self.base_version_id = base_version_id
        self.target_version_id = target_version_id


def _load_ontology(version_id: int, tenant_id: str | None = None) -> OntologySpec:
    """Load OntologySpec from PG version store."""
    from app.db.pg_client import get_version

    row = get_version(version_id, tenant_id=tenant_id)
    if row is None:
        raise VersionNotFoundError(version_id)
    return OntologySpec(**row["ontology_json"])


@router.post("/ontology/diff", response_model=OntologyDiff)
async def compute_diff_endpoint(
    base_version_id: int,
    target_version_id: int,
):
    """Compute diff between two ontology versions."""
    from app.schema_evolution.diff import compute_diff

    base_ont = _load_ontology(base_version_id)
    target_ont = _load_ontology(target_version_id)

    return compute_diff(base_ont, target_ont, base_version_id, target_version_id)


@router.post("/ontology/impact")
async def compute_impact_endpoint(
    base_version_id: int,
    target_version_id: int,
):
    """Compute diff + impact analysis against live KG."""
    from app.schema_evolution.diff import compute_diff
    from app.schema_evolution.impact import analyze_impact

    base_ont = _load_ontology(base_version_id)
    target_ont = _load_ontology(target_version_id)
    diff = compute_diff(base_ont, target_ont, base_version_id, target_version_id)
    impact = analyze_impact(diff, base_ont, target_ont)

    return {"diff": diff, "impact": impact}


@router.post("/kg/migrate", status_code=202, response_model=MigrationResponse)
async def start_migration(
    request: MigrationRequest,
    background_tasks: BackgroundTasks,
):
    """Launch incremental migration job."""
    from app.schema_evolution.service import create_migration_job, run_migration

    base_ont = _load_ontology(request.base_version_id)
    target_ont = _load_ontology(request.target_version_id)

    # CSV data (optional)
    csv_data = None
    if request.csv_session_id:
        from app.csv_import.parser import pop_csv_session
        csv_data = pop_csv_session(request.csv_session_id)

    job_id = f"mig-{uuid.uuid4().hex[:12]}"
    job = create_migration_job(job_id, request.base_version_id, request.target_version_id)

    background_tasks.add_task(
        run_migration,
        job_id=job_id,
        base_ontology=base_ont,
        target_ontology=target_ont,
        base_version_id=request.base_version_id,
        target_version_id=request.target_version_id,
        erd=request.erd,
        csv_data=csv_data,
        dry_run=request.dry_run,
    )

    return job


@router.get("/kg/migrate/{job_id}", response_model=MigrationResponse)
async def get_migration_status(job_id: str):
    """Poll migration job status."""
    from app.schema_evolution.service import get_migration_job

    job = get_migration_job(job_id)
    if job is None:
        raise MigrationNotFoundError(job_id)
    return job
