"""Multi-tenancy foundation tests — tenant isolation and backward compat."""

from __future__ import annotations

import pytest

from app.tenant import (
    DEFAULT_TENANT_DB,
    get_tenant_map,
    prefixed_label,
    prefix_cypher_labels,
    tenant_db_id,
    tenant_label_prefix,
)


# ── tenant.py utility tests ─────────────────────────────────────


def test_tenant_label_prefix_none():
    """Single-tenant mode returns empty prefix."""
    assert tenant_label_prefix(None) == ""


def test_tenant_label_prefix_with_id():
    """Multi-tenant mode returns t_{id}_ prefix."""
    assert tenant_label_prefix("acme") == "t_acme_"


def test_prefixed_label_none():
    """No prefix in single-tenant mode."""
    assert prefixed_label(None, "Customer") == "Customer"


def test_prefixed_label_with_tenant():
    """Applies prefix in multi-tenant mode."""
    assert prefixed_label("acme", "Customer") == "t_acme_Customer"


def test_tenant_db_id_none():
    """None tenant_id maps to _default_ sentinel."""
    assert tenant_db_id(None) == DEFAULT_TENANT_DB


def test_tenant_db_id_set():
    """Explicit tenant_id passes through."""
    assert tenant_db_id("acme") == "acme"


def test_prefix_cypher_labels_noop():
    """No prefixing when tenant_id is None."""
    cypher = "MATCH (c:Customer)-[:PLACED]->(o:Order) RETURN c, o"
    assert prefix_cypher_labels(cypher, None, ["Customer", "Order"]) == cypher


def test_prefix_cypher_labels_with_tenant():
    """Prefixes known labels in Cypher."""
    cypher = "MATCH (c:Customer)-[:PLACED]->(o:Order) RETURN c, o"
    result = prefix_cypher_labels(cypher, "acme", ["Customer", "Order"])
    assert "t_acme_Customer" in result
    assert "t_acme_Order" in result
    assert "PLACED" in result  # relationship types NOT prefixed


def test_prefix_cypher_labels_longer_first():
    """Longer labels are replaced before shorter to avoid partial matches."""
    cypher = "MATCH (oi:OrderItem)-[:OF]->(o:Order) RETURN oi, o"
    result = prefix_cypher_labels(cypher, "t1", ["OrderItem", "Order"])
    assert "t_t1_OrderItem" in result
    assert "t_t1_Order" in result


def test_get_tenant_map_empty(monkeypatch):
    """No TENANT_KEYS env → empty map."""
    from app.config import settings
    monkeypatch.setattr(settings, "tenant_keys", None)
    assert get_tenant_map() == {}


def test_get_tenant_map_valid(monkeypatch):
    """Valid JSON TENANT_KEYS → parsed dict."""
    from app.config import settings
    monkeypatch.setattr(settings, "tenant_keys", '{"key1": "acme", "key2": "beta"}')
    result = get_tenant_map()
    assert result == {"key1": "acme", "key2": "beta"}


# ── Entity cache tenant scoping ──────────────────────────────────


def test_invalidate_entity_cache_all():
    """invalidate_entity_cache(None) clears all entries."""
    from app.cache import cache, make_key
    from app.query.local_search import invalidate_entity_cache

    # Seed cache data via unified cache layer
    cache.set(make_key("entities", "acme"), {"Customer": ["Alice"]})
    cache.set(make_key("entities", "beta"), {"Product": ["Widget"]})

    invalidate_entity_cache(None)  # clear all

    assert cache.get(make_key("entities", "acme")) is None
    assert cache.get(make_key("entities", "beta")) is None


def test_invalidate_entity_cache_specific():
    """invalidate_entity_cache('acme') clears only that tenant."""
    from app.cache import cache, make_key
    from app.query.local_search import invalidate_entity_cache

    cache.set(make_key("entities", "acme"), {"Customer": ["Alice"]})
    cache.set(make_key("entities", "beta"), {"Product": ["Widget"]})

    invalidate_entity_cache("acme")

    assert cache.get(make_key("entities", "acme")) is None
    assert cache.get(make_key("entities", "beta")) is not None
    # Cleanup
    cache.delete(make_key("entities", "beta"))


# ── Auth middleware tests ────────────────────────────────────────


@pytest.fixture
def _app():
    from app.main import create_app
    return create_app()


@pytest.fixture
async def api_client(_app):
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health_always_public(api_client, monkeypatch):
    """/health is public — accessible even with auth configured."""
    from app.config import settings
    monkeypatch.setattr(settings, "app_api_key", "secret")
    monkeypatch.setattr(settings, "tenant_keys", None)

    resp = await api_client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_no_auth_mode(api_client, monkeypatch):
    """Without API keys configured, requests go through."""
    from app.config import settings
    monkeypatch.setattr(settings, "app_api_key", None)
    monkeypatch.setattr(settings, "tenant_keys", None)

    resp = await api_client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_single_key_valid(api_client, monkeypatch):
    """Single API key mode: valid key on non-public path → passes auth."""
    from app.config import settings
    monkeypatch.setattr(settings, "app_api_key", "test-key-123")
    monkeypatch.setattr(settings, "tenant_keys", None)

    resp = await api_client.get(
        "/api/v1/health",
        headers={"X-API-Key": "test-key-123"},
    )
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_single_key_invalid(api_client, monkeypatch):
    """Single API key mode: invalid key on non-public path → 401."""
    from app.config import settings
    monkeypatch.setattr(settings, "app_api_key", "test-key-123")
    monkeypatch.setattr(settings, "tenant_keys", None)

    # Use a non-public endpoint for this test
    resp = await api_client.post(
        "/api/v1/ontology/generate",
        json={"erd": {"tables": [], "foreign_keys": []}, "skip_llm": True},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_multi_tenant_valid(api_client, monkeypatch):
    """Multi-tenant mode: valid tenant key → passes auth."""
    from app.config import settings
    monkeypatch.setattr(settings, "app_api_key", None)
    monkeypatch.setattr(settings, "tenant_keys", '{"key-acme": "acme"}')

    resp = await api_client.get(
        "/api/v1/health",
        headers={"X-API-Key": "key-acme"},
    )
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_multi_tenant_invalid(api_client, monkeypatch):
    """Multi-tenant mode: unknown key on non-public path → 401."""
    from app.config import settings
    monkeypatch.setattr(settings, "app_api_key", None)
    monkeypatch.setattr(settings, "tenant_keys", '{"key-acme": "acme"}')

    resp = await api_client.post(
        "/api/v1/ontology/generate",
        json={"erd": {"tables": [], "foreign_keys": []}, "skip_llm": True},
        headers={"X-API-Key": "unknown-key"},
    )
    assert resp.status_code == 401
