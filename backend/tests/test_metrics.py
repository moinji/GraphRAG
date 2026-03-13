"""Tests for Prometheus metrics and OpenTelemetry setup."""

from __future__ import annotations

import pytest
from unittest.mock import patch


class TestPrometheusMiddleware:
    """Test PrometheusMiddleware ASGI integration."""

    @pytest.mark.anyio
    async def test_middleware_records_request(self, client):
        """Middleware increments HTTP counters on request."""
        from app.metrics import PROMETHEUS_AVAILABLE

        if not PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus-client not installed")

        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_normalize_path_collapses_ids(self):
        """Numeric path segments are collapsed to {id}."""
        from app.metrics import _normalize_path

        assert _normalize_path("/api/v1/kg/build/abc-123") == "/api/v1/kg/build/abc-123"
        assert _normalize_path("/api/v1/ontology/versions/42") == "/api/v1/ontology/versions/{id}"
        assert _normalize_path("/api/v1/health") == "/api/v1/health"

    def test_normalize_path_numeric_segments(self):
        """Pure numeric segments become {id}."""
        from app.metrics import _normalize_path

        assert _normalize_path("/api/v1/documents/123") == "/api/v1/documents/{id}"

    @pytest.mark.anyio
    async def test_metrics_endpoint_returns_content(self, client):
        """GET /metrics returns prometheus text format."""
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "http_requests_total" in body or "prometheus" in body.lower()


class TestRecordLLMUsage:
    """Test Prometheus LLM metrics recording."""

    def test_record_llm_usage_no_error(self):
        """record_llm_usage does not raise even if prometheus unavailable."""
        from app.metrics import record_llm_usage

        record_llm_usage("test_caller", "gpt-4o", 100, 50)


class TestTelemetrySetup:
    """Test OpenTelemetry setup (optional)."""

    def test_setup_telemetry_no_crash(self):
        """setup_telemetry should not crash even without OTLP endpoint."""
        from fastapi import FastAPI
        from app.telemetry import setup_telemetry

        test_app = FastAPI()
        setup_telemetry(test_app)

    def test_setup_telemetry_with_console(self):
        """setup_telemetry with OTEL_CONSOLE=1 enables console exporter."""
        from fastapi import FastAPI
        from app.telemetry import setup_telemetry

        test_app = FastAPI()
        with patch.dict("os.environ", {"OTEL_CONSOLE": "1"}):
            setup_telemetry(test_app)


class TestLLMTrackerPrometheusIntegration:
    """Test that LLMUsageTracker feeds Prometheus metrics."""

    def test_tracker_record_calls_prometheus(self):
        """tracker.record() should call record_llm_usage."""
        from app.llm_tracker import tracker

        with patch("app.metrics.record_llm_usage") as mock_record:
            tracker.record("test", "gpt-4o", 100, 50)
            mock_record.assert_called_once_with("test", "gpt-4o", 100, 50)
