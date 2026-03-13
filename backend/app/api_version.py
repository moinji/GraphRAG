"""API versioning middleware and utilities.

Adds version headers to responses and supports multiple API versions.

Versions:
  v1 — original API (maintained, no breaking changes)
  v2 — streamlined API (consolidated endpoints, consistent naming)

Usage::

    # In main.py:
    application.add_middleware(APIVersionMiddleware)

    # In routers:
    from app.api_version import API_V2_PREFIX
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Current API versions
API_V1 = "1.0"
API_V2 = "2.0"
API_LATEST = API_V2
API_V1_PREFIX = "/api/v1"
API_V2_PREFIX = "/api/v2"

# v1 endpoints marked for deprecation (will be removed in future)
_V1_DEPRECATED_PATHS: set[str] = set()  # None deprecated yet


class APIVersionMiddleware:
    """Pure ASGI middleware that adds API version headers."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        is_v1 = path.startswith(API_V1_PREFIX)
        is_v2 = path.startswith(API_V2_PREFIX)
        is_deprecated = path in _V1_DEPRECATED_PATHS

        async def send_with_version(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))

                # Add API version header
                if is_v2:
                    headers.append((b"x-api-version", API_V2.encode()))
                elif is_v1:
                    headers.append((b"x-api-version", API_V1.encode()))

                # Add deprecation header for deprecated v1 endpoints
                if is_deprecated:
                    headers.append((b"deprecation", b"true"))
                    headers.append(
                        (b"sunset", b"2026-06-01")
                    )

                message = {**message, "headers": headers}

            await send(message)

        await self.app(scope, receive, send_with_version)
