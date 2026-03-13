"""Security headers middleware — CSP, HSTS, X-Content-Type-Options, etc.

Active in production (APP_ENV=production). Development mode adds relaxed
CSP to allow Vite dev server hot reload.
"""

from __future__ import annotations

import os

from starlette.types import ASGIApp, Receive, Scope, Send


# Production CSP: strict, API-only backend
_PROD_CSP = "; ".join([
    "default-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "form-action 'none'",
])

# Development CSP: relaxed for dev tools
_DEV_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "connect-src 'self' ws: wss:",
    "img-src 'self' data:",
])

_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"x-xss-protection", b"0"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


class SecurityHeadersMiddleware:
    """Pure ASGI middleware that injects security headers into responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        is_prod = os.getenv("APP_ENV", "development") == "production"
        csp = _PROD_CSP if is_prod else _DEV_CSP
        self._extra_headers = [
            *_SECURITY_HEADERS,
            (b"content-security-policy", csp.encode()),
        ]
        if is_prod:
            self._extra_headers.append(
                (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.extend(self._extra_headers)
                message = {**message, "headers": raw_headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
