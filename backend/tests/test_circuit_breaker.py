"""Tests for circuit breaker pattern and graceful degradation."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from app.circuit_breaker import CircuitBreaker, CircuitState


# ── CircuitBreaker unit tests ──────────────────────────────────────


class TestCircuitBreakerStates:
    """Test state transitions."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED

    def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_opens_at_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_blocks_requests(self):
        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_closed_allows_requests(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        assert cb.allow_request() is True

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_limited_requests(self):
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=0.1, half_open_max_calls=1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        # First request allowed (probe)
        assert cb.allow_request() is True
        # Second request blocked
        assert cb.allow_request() is False

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.allow_request()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.allow_request()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # After success, failures reset — one more failure shouldn't trip
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_manual_reset(self):
        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_get_status(self):
        cb = CircuitBreaker("neo4j", failure_threshold=5, reset_timeout=30.0)
        cb.record_failure()
        status = cb.get_status()
        assert status["name"] == "neo4j"
        assert status["state"] == "closed"
        assert status["failure_count"] == 1
        assert status["failure_threshold"] == 5
        assert status["reset_timeout_s"] == 30.0


# ── Global breaker instances ──────────────────────────────────────


def test_global_breakers_exist():
    from app.circuit_breaker import neo4j_breaker, pg_breaker

    assert neo4j_breaker.name == "neo4j"
    assert pg_breaker.name == "postgres"
    assert neo4j_breaker.state == CircuitState.CLOSED
    assert pg_breaker.state == CircuitState.CLOSED


# ── Graceful degradation in pipeline ──────────────────────────────


@pytest.fixture(autouse=True)
def _reset_breakers():
    """Reset global breakers before each test."""
    from app.circuit_breaker import neo4j_breaker, pg_breaker

    neo4j_breaker.reset()
    pg_breaker.reset()
    yield
    neo4j_breaker.reset()
    pg_breaker.reset()


class TestPipelineGracefulDegradation:
    """Test that the query pipeline degrades gracefully on Neo4j outage."""

    def test_degraded_response_when_neo4j_down_no_cache(self):
        """When Neo4j is down and no cache, return degraded error response."""
        from app.circuit_breaker import neo4j_breaker

        # Trip the breaker
        for _ in range(5):
            neo4j_breaker.record_failure()

        with patch("app.query.pipeline.route_question") as mock_route:
            mock_route.return_value = ("one_hop_out", "cypher_traverse", {}, {}, "rule")

            with patch("app.query.pipeline.fill_template") as mock_fill:
                mock_fill.return_value = ("MATCH (n) RETURN n", {})

                from app.query.pipeline import run_query

                resp = run_query("What products?", mode="a")
                assert resp.degraded is True
                assert resp.error == "neo4j_unavailable"
                assert "unavailable" in resp.answer.lower() or "연결" in resp.answer

    def test_degraded_response_serves_stale_cache(self):
        """When Neo4j is down but cache exists, serve stale cached answer."""
        from app.circuit_breaker import neo4j_breaker
        from app.models.schemas import QueryResponse

        question = "How many products?"
        cached_resp = QueryResponse(
            question=question,
            answer="Found 10 products.",
            cypher="MATCH (n:Product) RETURN count(n)",
            paths=[],
            template_id="count_all",
            route="cypher_agg",
            matched_by="rule",
            mode="a",
        )

        # Trip the breaker
        for _ in range(5):
            neo4j_breaker.record_failure()

        # Mock _cache_get: first call (LRU check) returns None,
        # second call (degradation fallback) returns stale data
        call_count = {"n": 0}
        def _mock_cache_get(q, tid):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # LRU miss
            return cached_resp  # stale cache hit for degradation

        with patch("app.query.pipeline.route_question") as mock_route:
            mock_route.return_value = ("count_all", "cypher_agg", {}, {}, "rule")

            with patch("app.query.pipeline.fill_template") as mock_fill:
                mock_fill.return_value = ("MATCH (n:Product) RETURN count(n)", {})

                with patch("app.query.pipeline._cache_get", side_effect=_mock_cache_get):
                    from app.query.pipeline import run_query

                    resp = run_query(question, mode="a")
                    assert resp.degraded is True
                    assert resp.cached is True
                    assert resp.answer == "Found 10 products."

    def test_normal_response_not_degraded(self):
        """Normal successful responses have degraded=False."""
        with patch("app.query.pipeline.route_question") as mock_route:
            mock_route.return_value = ("one_hop_out", "cypher_traverse", {}, {}, "rule")

            with patch("app.query.pipeline.fill_template") as mock_fill:
                mock_fill.return_value = ("MATCH (n) RETURN n", {})

                with patch("app.query.pipeline._execute_cypher") as mock_exec:
                    mock_exec.return_value = [{"result": "test"}]

                    from app.query.pipeline import run_query

                    resp = run_query("What products?", mode="a")
                    assert resp.degraded is False

    def test_circuit_breaker_in_execute_cypher_records_success(self):
        """_execute_cypher records success on the breaker."""
        from app.circuit_breaker import neo4j_breaker

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = []

        with patch("app.query.pipeline.get_driver", return_value=mock_driver):
            from app.query.pipeline import _execute_cypher

            _execute_cypher("RETURN 1", {})
            # Breaker should be closed with 0 failures
            status = neo4j_breaker.get_status()
            assert status["state"] == "closed"

    def test_circuit_breaker_in_execute_cypher_records_failure(self):
        """_execute_cypher records failure on the breaker."""
        from app.circuit_breaker import neo4j_breaker
        from app.exceptions import CypherExecutionError

        with patch("app.query.pipeline.get_driver", side_effect=Exception("connection refused")):
            from app.query.pipeline import _execute_cypher

            with pytest.raises(CypherExecutionError):
                _execute_cypher("RETURN 1", {})

        status = neo4j_breaker.get_status()
        assert status["failure_count"] == 1


# ── Health endpoint integration ───────────────────────────────────


@pytest.mark.anyio
class TestHealthCircuitBreaker:
    """Test that health endpoint reports circuit breaker state."""

    async def test_health_includes_circuit_breaker_state(self, client):
        resp = await client.get("/api/v1/health")
        data = resp.json()
        # Circuit breaker state should be present in service health
        assert "circuit_breaker" in data["neo4j"]
        assert "circuit_breaker" in data["postgres"]
        assert data["neo4j"]["circuit_breaker"] in ("closed", "open", "half_open")
        assert data["postgres"]["circuit_breaker"] in ("closed", "open", "half_open")
