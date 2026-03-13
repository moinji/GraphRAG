"""Tests for security headers middleware."""

from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_x_content_type_options(client):
    """Response includes X-Content-Type-Options: nosniff."""
    resp = await client.get("/api/v1/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.anyio
async def test_x_frame_options(client):
    """Response includes X-Frame-Options: DENY."""
    resp = await client.get("/api/v1/health")
    assert resp.headers.get("x-frame-options") == "DENY"


@pytest.mark.anyio
async def test_referrer_policy(client):
    """Response includes Referrer-Policy."""
    resp = await client.get("/api/v1/health")
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.anyio
async def test_permissions_policy(client):
    """Response includes Permissions-Policy."""
    resp = await client.get("/api/v1/health")
    assert "camera=()" in resp.headers.get("permissions-policy", "")


@pytest.mark.anyio
async def test_csp_present(client):
    """Response includes Content-Security-Policy."""
    resp = await client.get("/api/v1/health")
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src" in csp


@pytest.mark.anyio
async def test_dev_csp_allows_self(client):
    """In development mode, CSP allows 'self'."""
    resp = await client.get("/api/v1/health")
    csp = resp.headers.get("content-security-policy", "")
    # Dev mode (default) should have 'self'
    assert "'self'" in csp


def test_prod_csp_is_strict():
    """Production CSP is strict (default-src 'none')."""
    from app.security_headers import _PROD_CSP

    assert "default-src 'none'" in _PROD_CSP
    assert "frame-ancestors 'none'" in _PROD_CSP


def test_dev_csp_allows_websocket():
    """Development CSP allows WebSocket for HMR."""
    from app.security_headers import _DEV_CSP

    assert "ws:" in _DEV_CSP
