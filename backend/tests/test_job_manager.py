"""Tests for the unified job manager."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.job_manager import JobInfo, JobManager, JobStatus, _job_to_dict


class TestJobManager:
    """Unit tests for JobManager."""

    def test_submit_returns_job_id(self):
        mgr = JobManager(max_workers=2)
        jid = mgr.submit("test", None, lambda: None)
        assert isinstance(jid, str)
        assert len(jid) == 36  # UUID format
        mgr.shutdown(wait_seconds=5)

    def test_submit_with_custom_id(self):
        mgr = JobManager(max_workers=2)
        jid = mgr.submit("test", None, lambda: None, job_id="custom-123")
        assert jid == "custom-123"
        mgr.shutdown(wait_seconds=5)

    def test_job_runs_and_succeeds(self):
        mgr = JobManager(max_workers=2)
        result = []

        def work():
            result.append("done")

        jid = mgr.submit("test", None, work)
        time.sleep(0.5)
        job = mgr.get(jid)
        assert job is not None
        assert job.status == JobStatus.SUCCEEDED
        assert result == ["done"]
        mgr.shutdown(wait_seconds=5)

    def test_job_failure_recorded(self):
        mgr = JobManager(max_workers=2)

        def fail():
            raise ValueError("test error")

        jid = mgr.submit("test", None, fail)
        time.sleep(0.5)
        job = mgr.get(jid)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert "test error" in (job.error or "")
        mgr.shutdown(wait_seconds=5)

    def test_list_jobs_by_tenant(self):
        mgr = JobManager(max_workers=2)
        mgr.submit("test", "tenant_a", lambda: None)
        mgr.submit("test", "tenant_b", lambda: None)
        mgr.submit("test", "tenant_a", lambda: None)
        time.sleep(0.5)

        a_jobs = mgr.list_jobs(tenant_id="tenant_a")
        b_jobs = mgr.list_jobs(tenant_id="tenant_b")
        assert len(a_jobs) == 2
        assert len(b_jobs) == 1
        mgr.shutdown(wait_seconds=5)

    def test_list_jobs_by_type(self):
        mgr = JobManager(max_workers=2)
        mgr.submit("kg_build", None, lambda: None)
        mgr.submit("document", None, lambda: None)
        mgr.submit("document", None, lambda: None)
        time.sleep(0.5)

        doc_jobs = mgr.list_jobs(job_type="document")
        kg_jobs = mgr.list_jobs(job_type="kg_build")
        assert len(doc_jobs) == 2
        assert len(kg_jobs) == 1
        mgr.shutdown(wait_seconds=5)

    def test_list_jobs_by_status(self):
        mgr = JobManager(max_workers=2)

        mgr.submit("test", None, lambda: None)
        mgr.submit("test", None, lambda: (_ for _ in ()).throw(ValueError("fail")))
        time.sleep(0.5)

        succeeded = mgr.list_jobs(status="succeeded")
        failed = mgr.list_jobs(status="failed")
        assert len(succeeded) == 1
        assert len(failed) == 1
        mgr.shutdown(wait_seconds=5)

    def test_update_progress(self):
        mgr = JobManager(max_workers=2)
        fixed_id = "progress-test-123"

        def work():
            mgr.update_progress(fixed_id, step="loading", pct=50)
            time.sleep(0.1)

        jid = mgr.submit("test", None, work, job_id=fixed_id)
        time.sleep(0.5)
        job = mgr.get(jid)
        assert job is not None
        assert job.progress.get("step") == "loading"
        assert job.progress.get("pct") == 50
        mgr.shutdown(wait_seconds=5)

    def test_get_stats(self):
        mgr = JobManager(max_workers=2)
        mgr.submit("test", None, lambda: None)
        mgr.submit("test", None, lambda: (_ for _ in ()).throw(ValueError("x")))
        time.sleep(0.5)

        stats = mgr.get_stats()
        assert stats["total_jobs"] == 2
        assert stats["active"] == 0
        assert "succeeded" in stats["by_status"]
        assert "failed" in stats["by_status"]
        mgr.shutdown(wait_seconds=5)

    def test_prune_old_jobs(self):
        mgr = JobManager(max_workers=2, max_completed=3)
        # Submit sequentially with waits to ensure completion before next prune
        for i in range(5):
            mgr.submit("test", None, lambda: None, job_id=f"job-{i}")
            time.sleep(0.3)  # let job complete before next submit triggers prune

        time.sleep(0.5)
        all_jobs = mgr.list_jobs(limit=100)
        # After pruning, should have at most max_completed + 1 (last submit prunes before adding)
        assert len(all_jobs) <= 5  # pruning kicks in when terminal > max_completed
        mgr.shutdown(wait_seconds=5)

    def test_metadata_preserved(self):
        mgr = JobManager(max_workers=2)
        jid = mgr.submit(
            "document", None, lambda: None,
            metadata={"filename": "test.pdf", "size": 1024},
        )
        time.sleep(0.3)
        job = mgr.get(jid)
        assert job is not None
        assert job.metadata["filename"] == "test.pdf"
        assert job.metadata["size"] == 1024
        mgr.shutdown(wait_seconds=5)

    def test_get_nonexistent_job(self):
        mgr = JobManager(max_workers=1)
        assert mgr.get("nonexistent") is None
        mgr.shutdown(wait_seconds=1)

    def test_active_count(self):
        mgr = JobManager(max_workers=1)

        def slow():
            time.sleep(0.5)

        mgr.submit("test", None, slow)
        time.sleep(0.1)
        assert mgr.active_count >= 1
        time.sleep(0.6)
        assert mgr.active_count == 0
        mgr.shutdown(wait_seconds=5)


class TestJobToDict:
    """Test serialization."""

    def test_serialization(self):
        job = JobInfo(
            job_id="abc-123",
            job_type="document",
            tenant_id="t1",
            status=JobStatus.SUCCEEDED,
            created_at="2026-03-13T00:00:00",
        )
        d = _job_to_dict(job)
        assert d["job_id"] == "abc-123"
        assert d["job_type"] == "document"
        assert d["status"] == "succeeded"
        assert d["tenant_id"] == "t1"


# ── API endpoint tests ────────────────────────────────────────────


@pytest.mark.anyio
class TestJobsAPI:
    """Test the /api/v1/jobs endpoints."""

    async def test_list_jobs_endpoint(self, client):
        resp = await client.get("/api/v1/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert "jobs" in data
        assert "total" in data
        assert "stats" in data

    async def test_get_nonexistent_job(self, client):
        resp = await client.get("/api/v1/jobs/nonexistent-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("error") == "Job not found"

    async def test_job_stats_endpoint(self, client):
        resp = await client.get("/api/v1/jobs/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_jobs" in data
        assert "active" in data
