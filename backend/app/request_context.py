"""Request context middleware — adds request_id and logs latency.

Uses pure ASGI middleware (not BaseHTTPMiddleware) to avoid
request body consumption issues with trio.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    """Pure ASGI middleware: injects X-Request-ID and logs request latency."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode() or uuid.uuid4().hex[:12]
        path = scope.get("path", "")
        method = scope.get("method", "")
        t0 = time.perf_counter()

        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                # Inject X-Request-ID into response headers
                raw_headers = list(message.get("headers", []))
                raw_headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": raw_headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if path != "/api/v1/health":
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.info(
                "%s %s %d (%.1fms)",
                method,
                path,
                status_code,
                latency_ms,
                extra={"request_id": request_id, "latency_ms": latency_ms},
            )
