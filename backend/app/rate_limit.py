"""Per-tenant + per-IP rate limiter middleware (pure ASGI).

- Tenant-aware: uses tenant_id from scope.state (set by APIKeyMiddleware)
- Falls back to client IP when no tenant_id
- Per-tenant quotas via TENANT_RATE_LIMITS env var (JSON)
- Adds X-RateLimit-* response headers
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Default: 60 requests per minute
DEFAULT_RATE = 60
DEFAULT_WINDOW = 60  # seconds

# Skip paths
_SKIP_PATHS = frozenset({"/api/v1/health", "/metrics"})


def _load_tenant_limits() -> dict[str, int]:
    """Load per-tenant rate limits from TENANT_RATE_LIMITS env var."""
    raw = os.getenv("TENANT_RATE_LIMITS", "")
    if not raw:
        return {}
    try:
        limits = json.loads(raw)
        if isinstance(limits, dict):
            return {k: int(v) for k, v in limits.items()}
    except (json.JSONDecodeError, ValueError):
        logger.warning("Invalid TENANT_RATE_LIMITS JSON: %s", raw)
    return {}


class RateLimitMiddleware:
    """Pure ASGI sliding-window rate limiter — tenant-aware with IP fallback."""

    def __init__(
        self,
        app: ASGIApp,
        rate: int = DEFAULT_RATE,
        window: int = DEFAULT_WINDOW,
    ) -> None:
        self.app = app
        self.default_rate = rate
        self.window = window
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._tenant_limits = _load_tenant_limits()
        if self._tenant_limits:
            logger.info("Per-tenant rate limits: %s", self._tenant_limits)

    def _get_key_and_limit(self, scope: Scope) -> tuple[str, int]:
        """Return (rate_limit_key, max_requests) for this request."""
        state = scope.get("state", {})
        tenant_id = state.get("tenant_id")

        if tenant_id:
            limit = self._tenant_limits.get(tenant_id, self.default_rate)
            return f"tenant:{tenant_id}", limit

        # Fall back to IP
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        return f"ip:{ip}", self.default_rate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        key, limit = self._get_key_and_limit(scope)
        now = time.monotonic()
        cutoff = now - self.window

        # Prune old entries
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]
        hits = self._hits[key]
        remaining = max(0, limit - len(hits))

        if len(hits) >= limit:
            # 429 Too Many Requests
            body = json.dumps(
                {"detail": "Rate limit exceeded. Please try again later."}
            ).encode()
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                    [b"retry-after", str(self.window).encode()],
                    [b"x-ratelimit-limit", str(limit).encode()],
                    [b"x-ratelimit-remaining", b"0"],
                    [b"x-ratelimit-reset", str(self.window).encode()],
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        hits.append(now)
        remaining = max(0, limit - len(hits))

        # Inject rate limit headers into response
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.extend([
                    (b"x-ratelimit-limit", str(limit).encode()),
                    (b"x-ratelimit-remaining", str(remaining).encode()),
                    (b"x-ratelimit-reset", str(self.window).encode()),
                ])
                message = {**message, "headers": raw_headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
