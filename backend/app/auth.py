"""API key authentication middleware (pure ASGI) with multi-tenancy support.

Modes:
1. No auth (development): APP_API_KEY and TENANT_KEYS both unset → bypass
2. Single-tenant: APP_API_KEY set → single key, tenant_id=None
3. Multi-tenant: TENANT_KEYS set → key→tenant mapping, tenant_id injected

Uses pure ASGI middleware (not BaseHTTPMiddleware) to avoid
body-consumption issues with multipart uploads on trio backend.
"""

from __future__ import annotations

import json
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings

logger = logging.getLogger(__name__)

# Paths that never require auth
_PUBLIC_PATHS = frozenset({
    "/api/v1/health",
    "/docs",
    "/openapi.json",
    "/redoc",
})


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith("/docs")


def _extract_key_from_headers(headers: list[tuple[bytes, bytes]]) -> str | None:
    """Extract API key from raw ASGI headers."""
    for name, value in headers:
        if name == b"x-api-key":
            return value.decode("latin-1")
        if name == b"authorization":
            auth = value.decode("latin-1")
            if auth.lower().startswith("bearer "):
                return auth[7:].strip()
    return None


async def _send_401(send: Send) -> None:
    body = json.dumps({"detail": "Invalid or missing API key"}).encode()
    await send({
        "type": "http.response.start",
        "status": 401,
        "headers": [
            [b"content-type", b"application/json"],
            [b"content-length", str(len(body)).encode()],
        ],
    })
    await send({"type": "http.response.body", "body": body})


class APIKeyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Determine auth mode
        from app.tenant import get_tenant_map
        tenant_map = get_tenant_map()
        has_single_key = bool(settings.app_api_key)
        has_multi_tenant = bool(tenant_map)

        # No auth configured → development mode (tenant_id=None)
        if not has_single_key and not has_multi_tenant:
            scope.setdefault("state", {})["tenant_id"] = None
            await self.app(scope, receive, send)
            return

        # Public paths skip auth
        path = scope.get("path", "")
        if _is_public(path):
            scope.setdefault("state", {})["tenant_id"] = None
            await self.app(scope, receive, send)
            return

        # Extract key from headers
        headers = scope.get("headers", [])
        provided_key = _extract_key_from_headers(headers)

        # Multi-tenant mode: look up key in tenant map
        if has_multi_tenant:
            if provided_key is None:
                await _send_401(send)
                return
            tenant_id = tenant_map.get(provided_key)
            if tenant_id is None:
                # Not in tenant map; try single-key fallback
                if has_single_key and provided_key == settings.app_api_key:
                    scope.setdefault("state", {})["tenant_id"] = None
                    await self.app(scope, receive, send)
                    return
                await _send_401(send)
                return
            scope.setdefault("state", {})["tenant_id"] = tenant_id
            await self.app(scope, receive, send)
            return

        # Single-tenant mode
        if provided_key != settings.app_api_key:
            await _send_401(send)
            return
        scope.setdefault("state", {})["tenant_id"] = None
        await self.app(scope, receive, send)
