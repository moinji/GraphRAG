"""Circuit breaker pattern for external service calls.

Prevents cascading failures when Neo4j or PostgreSQL is down by
fast-failing after repeated errors and periodically retesting.

States:
  CLOSED   — normal operation, requests pass through
  OPEN     — service is down, requests fail fast
  HALF_OPEN — testing recovery, limited requests allowed

Usage::

    from app.circuit_breaker import neo4j_breaker, pg_breaker

    if neo4j_breaker.allow_request():
        try:
            result = driver.session().run(...)
            neo4j_breaker.record_success()
        except Exception:
            neo4j_breaker.record_failure()
    else:
        # fast-fail or serve from cache
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker for a single service."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._get_state()

    def _get_state(self) -> CircuitState:
        """Internal state check (must hold lock)."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.reset_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(
                    "Circuit breaker [%s] transitioning OPEN -> HALF_OPEN",
                    self.name,
                )
        return self._state

    def allow_request(self) -> bool:
        """Check whether a request should be attempted."""
        with self._lock:
            state = self._get_state()
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            # OPEN
            return False

    def record_success(self) -> None:
        """Record a successful call — reset to CLOSED if in HALF_OPEN."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "Circuit breaker [%s] recovered: HALF_OPEN -> CLOSED",
                    self.name,
                )
                self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count += 1

    def record_failure(self) -> None:
        """Record a failed call — trip to OPEN if threshold reached."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    "Circuit breaker [%s] tripped: HALF_OPEN -> OPEN (probe failed)",
                    self.name,
                )
                self._state = CircuitState.OPEN
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                logger.warning(
                    "Circuit breaker [%s] tripped: CLOSED -> OPEN "
                    "(%d consecutive failures)",
                    self.name,
                    self._failure_count,
                )
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED (e.g. after admin action)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            logger.info("Circuit breaker [%s] manually reset to CLOSED", self.name)

    def get_status(self) -> dict[str, Any]:
        """Return breaker status for health/diagnostics."""
        with self._lock:
            state = self._get_state()
            return {
                "name": self.name,
                "state": state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "reset_timeout_s": self.reset_timeout,
            }


# ── Global breakers for core services ──────────────────────────────
neo4j_breaker = CircuitBreaker("neo4j", failure_threshold=5, reset_timeout=30.0)
pg_breaker = CircuitBreaker("postgres", failure_threshold=5, reset_timeout=30.0)
