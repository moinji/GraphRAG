"""KG Build endpoints — async job launch + status polling."""

from __future__ import annotations

import random
import time

from fastapi import APIRouter, BackgroundTasks

from app.csv_import.parser import delete_session, get_session
from app.db.pg_client import get_version
from app.exceptions import BuildJobNotFoundError, VersionConflictError, VersionNotFoundError
from app.kg_builder.service import create_job, get_job, run_kg_build
from app.models.schemas import KGBuildRequest, KGBuildResponse, OntologySpec

router = APIRouter(prefix="/api/v1/kg", tags=["kg-build"])


@router.post("/build", response_model=KGBuildResponse, status_code=202)
def start_kg_build(
    body: KGBuildRequest,
    background_tasks: BackgroundTasks,
) -> KGBuildResponse:
    """Launch an async KG build job. Returns 202 with queued status."""
    # Validate version exists and is approved
    version_row = get_version(body.version_id)
    if version_row is None:
        raise VersionNotFoundError(body.version_id)

    if version_row.get("status") != "approved":
        raise VersionConflictError(
            f"Version {body.version_id} must be approved before building KG"
        )

    # Build ontology from stored version
    ontology = OntologySpec(**version_row["ontology_json"])

    # Resolve CSV session data if provided
    csv_data = None
    if body.csv_session_id:
        csv_data = get_session(body.csv_session_id)
        if csv_data is None:
            raise BuildJobNotFoundError(body.csv_session_id)
        delete_session(body.csv_session_id)  # one-time consumption

    # Generate job ID
    ts = int(time.time())
    rand = f"{random.randint(0, 0xFFFF):04x}"
    job_id = f"build_{ts}_{rand}"

    # Create queued job
    job = create_job(job_id, body.version_id)

    # Schedule background task
    background_tasks.add_task(
        run_kg_build, job_id, body.version_id, body.erd, ontology, csv_data
    )

    return job


@router.get("/build/{job_id}", response_model=KGBuildResponse)
def get_kg_build_status(job_id: str) -> KGBuildResponse:
    """Poll KG build job status."""
    job = get_job(job_id)
    if job is None:
        raise BuildJobNotFoundError(job_id)
    return job
