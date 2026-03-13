"""Tests for API versioning middleware and v2 endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.anyio
class TestAPIVersionHeaders:
    """Test that API version headers are added to responses."""

    async def test_v1_endpoint_has_version_header(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.headers.get("x-api-version") == "1.0"

    async def test_v2_endpoint_has_version_header(self, client):
        resp = await client.get("/api/v2/version")
        assert resp.headers.get("x-api-version") == "2.0"

    async def test_non_api_endpoint_no_version_header(self, client):
        resp = await client.get("/metrics")
        assert "x-api-version" not in resp.headers


@pytest.mark.anyio
class TestV2Endpoints:
    """Test v2 API endpoints."""

    async def test_version_info(self, client):
        resp = await client.get("/api/v2/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current"] == "2.0"
        assert "1.0" in data["supported"]
        assert "2.0" in data["supported"]
        assert data["latest"] == "2.0"

    async def test_unified_status(self, client):
        resp = await client.get("/api/v2/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert "services" in data
        assert "neo4j" in data["services"]
        assert "postgres" in data["services"]
        assert "llm" in data["services"]
        # Circuit breaker info embedded
        assert "circuit_breaker" in data["services"]["neo4j"]
        assert "circuit_breaker" in data["services"]["postgres"]
        # Job stats
        assert "jobs" in data
        assert "total_jobs" in data["jobs"]

    async def test_v1_health_still_works(self, client):
        """v1 endpoints remain functional alongside v2."""
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
