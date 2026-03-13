"""Prometheus metrics for HTTP requests and LLM usage.

Provides ASGI middleware for automatic HTTP metric collection
and a ``/metrics`` endpoint for Prometheus scraping.
"""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    REGISTRY = CollectorRegistry()

    HTTP_REQUESTS_TOTAL = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
        registry=REGISTRY,
    )
    HTTP_REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        registry=REGISTRY,
    )
    HTTP_IN_PROGRESS = Gauge(
        "http_requests_in_progress",
        "HTTP requests currently in progress",
        ["method"],
        registry=REGISTRY,
    )
    LLM_TOKENS_TOTAL = Counter(
        "llm_tokens_total",
        "Total LLM tokens consumed",
        ["caller", "model", "type"],
        registry=REGISTRY,
    )
    LLM_CALLS_TOTAL = Counter(
        "llm_calls_total",
        "Total LLM API calls",
        ["caller", "model"],
        registry=REGISTRY,
    )

    PROMETHEUS_AVAILABLE = True

except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.debug("prometheus-client not installed — metrics disabled")


def record_llm_usage(
    caller: str, model: str, input_tokens: int, output_tokens: int
) -> None:
    """Record LLM token usage in Prometheus counters."""
    if not PROMETHEUS_AVAILABLE:
        return
    LLM_TOKENS_TOTAL.labels(caller=caller, model=model, type="input").inc(input_tokens)
    LLM_TOKENS_TOTAL.labels(caller=caller, model=model, type="output").inc(
        output_tokens
    )
    LLM_CALLS_TOTAL.labels(caller=caller, model=model).inc()


def _normalize_path(path: str) -> str:
    """Collapse dynamic path segments to reduce cardinality."""
    parts = path.rstrip("/").split("/")
    normalized = []
    for part in parts:
        if part.isdigit():
            normalized.append("{id}")
        else:
            normalized.append(part)
    return "/".join(normalized) or "/"


class PrometheusMiddleware:
    """Pure ASGI middleware for HTTP request metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not PROMETHEUS_AVAILABLE:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = _normalize_path(scope.get("path", "/"))

        # Skip /metrics itself to avoid recursion
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        HTTP_IN_PROGRESS.labels(method=method).inc()
        t0 = time.perf_counter()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - t0
            HTTP_REQUESTS_TOTAL.labels(
                method=method, path=path, status=str(status_code)
            ).inc()
            HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(duration)
            HTTP_IN_PROGRESS.labels(method=method).dec()


def metrics_endpoint():
    """Returns Prometheus metrics as text for scraping."""
    if not PROMETHEUS_AVAILABLE:
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(
            "# prometheus-client not installed\n", status_code=501
        )
    from fastapi.responses import Response

    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
