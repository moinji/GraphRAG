"""Unified background job manager.

Provides centralized job lifecycle management with:
- Job creation, status tracking, and progress updates
- Configurable concurrency via ThreadPoolExecutor
- Job listing per tenant, retry for failed jobs
- Graceful shutdown with active job drain

Usage::

    from app.job_manager import job_manager

    job_id = job_manager.submit("kg_build", tenant_id, my_func, arg1, arg2)
    status = job_manager.get(job_id)
    all_jobs = job_manager.list_jobs(tenant_id, job_type="kg_build")
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class JobInfo:
    """Tracks a single background job."""

    job_id: str
    job_type: str  # "kg_build", "document", etc.
    tenant_id: str | None
    status: JobStatus = JobStatus.QUEUED
    progress: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class JobManager:
    """Thread-safe background job manager with concurrency control."""

    def __init__(self, max_workers: int = 4, max_completed: int = 200) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobInfo] = {}
        self._max_completed = max_completed
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="job"
        )
        self._active_count = 0

    def submit(
        self,
        job_type: str,
        tenant_id: str | None,
        func: Callable[..., Any],
        *args: Any,
        job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Submit a background job. Returns the job ID."""
        if job_id is None:
            job_id = str(uuid.uuid4())

        now = datetime.now(timezone.utc).isoformat()
        job = JobInfo(
            job_id=job_id,
            job_type=job_type,
            tenant_id=tenant_id,
            status=JobStatus.QUEUED,
            created_at=now,
            metadata=metadata or {},
        )

        with self._lock:
            self._prune()
            self._jobs[job_id] = job
            self._active_count += 1

        self._executor.submit(self._run_wrapper, job_id, func, args, kwargs)
        logger.info("Job submitted: %s [%s] tenant=%s", job_id[:8], job_type, tenant_id)
        return job_id

    def _run_wrapper(
        self,
        job_id: str,
        func: Callable[..., Any],
        args: tuple,
        kwargs: dict,
    ) -> None:
        """Wrap function execution with status tracking."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(timezone.utc).isoformat()

        try:
            func(*args, **kwargs)
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = JobStatus.SUCCEEDED
                    job.completed_at = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            logger.error("Job %s failed: %s", job_id[:8], e, exc_info=True)
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.error = str(e)
                    job.completed_at = datetime.now(timezone.utc).isoformat()
        finally:
            with self._lock:
                self._active_count -= 1

    def get(self, job_id: str) -> JobInfo | None:
        """Get job info by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def update_progress(self, job_id: str, **kwargs: Any) -> None:
        """Update progress fields for a running job (called from within the job)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.progress.update(kwargs)

    def list_jobs(
        self,
        tenant_id: str | None = None,
        job_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[JobInfo]:
        """List jobs with optional filters."""
        with self._lock:
            jobs = list(self._jobs.values())

        if tenant_id is not None:
            jobs = [j for j in jobs if j.tenant_id == tenant_id]
        if job_type is not None:
            jobs = [j for j in jobs if j.job_type == job_type]
        if status is not None:
            jobs = [j for j in jobs if j.status.value == status]

        # Most recent first
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    @property
    def active_count(self) -> int:
        with self._lock:
            return self._active_count

    def shutdown(self, wait_seconds: int = 30) -> None:
        """Graceful shutdown — wait for active jobs then shut down executor."""
        if self._active_count > 0:
            logger.info(
                "Waiting for %d active job(s) to finish (max %ds)...",
                self._active_count,
                wait_seconds,
            )
            deadline = time.monotonic() + wait_seconds
            while self._active_count > 0 and time.monotonic() < deadline:
                time.sleep(0.5)
            if self._active_count > 0:
                logger.warning(
                    "Shutdown timeout: %d job(s) still active", self._active_count
                )

        self._executor.shutdown(wait=False)
        logger.info("Job manager shut down")

    def _prune(self) -> None:
        """Remove oldest completed jobs when exceeding max (must hold lock)."""
        terminal = [
            (jid, j)
            for jid, j in self._jobs.items()
            if j.status in (JobStatus.SUCCEEDED, JobStatus.FAILED)
        ]
        if len(terminal) <= self._max_completed:
            return
        terminal.sort(key=lambda x: x[1].completed_at or "")
        excess = len(terminal) - self._max_completed
        for jid, _ in terminal[:excess]:
            del self._jobs[jid]

    def get_stats(self) -> dict[str, Any]:
        """Return manager statistics."""
        with self._lock:
            statuses = {}
            for j in self._jobs.values():
                statuses[j.status.value] = statuses.get(j.status.value, 0) + 1
            return {
                "total_jobs": len(self._jobs),
                "active": self._active_count,
                "by_status": statuses,
            }


def _job_to_dict(job: JobInfo) -> dict[str, Any]:
    """Serialize JobInfo for API responses."""
    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "tenant_id": job.tenant_id,
        "status": job.status.value,
        "progress": job.progress,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "metadata": job.metadata,
    }


# Global singleton
job_manager = JobManager(max_workers=4, max_completed=200)
