"""Simple in-memory rate limiter middleware."""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Default: 60 requests per minute per IP
DEFAULT_RATE = 60
DEFAULT_WINDOW = 60  # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter by client IP."""

    def __init__(self, app, rate: int = DEFAULT_RATE, window: int = DEFAULT_WINDOW):
        super().__init__(app)
        self.rate = rate
        self.window = window
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Skip health check
        if request.url.path == "/api/v1/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - self.window

        # Prune old entries
        hits = self._hits[client_ip]
        self._hits[client_ip] = [t for t in hits if t > cutoff]
        hits = self._hits[client_ip]

        if len(hits) >= self.rate:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(self.window)},
            )

        hits.append(now)
        return await call_next(request)
