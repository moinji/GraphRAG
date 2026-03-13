"""Background job management API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.job_manager import JobStatus, _job_to_dict, job_manager
from app.tenant import get_tenant_id

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    request: Request,
    job_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List background jobs for the current tenant."""
    tenant_id = get_tenant_id(request)
    jobs = job_manager.list_jobs(
        tenant_id=tenant_id,
        job_type=job_type,
        status=status,
        limit=min(limit, 100),
    )
    return {
        "jobs": [_job_to_dict(j) for j in jobs],
        "total": len(jobs),
        "stats": job_manager.get_stats(),
    }


@router.get("/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """Get a single job by ID."""
    job = job_manager.get(job_id)
    if job is None:
        return {"error": "Job not found", "job_id": job_id}
    return _job_to_dict(job)


@router.get("/stats/summary")
def job_stats() -> dict[str, Any]:
    """Get job manager statistics."""
    return job_manager.get_stats()
