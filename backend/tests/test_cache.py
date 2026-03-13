"""Tests for unified cache layer."""

from __future__ import annotations

import time

from app.cache import InMemoryCache, hash_question, make_key


class TestMakeKey:
    def test_basic(self):
        assert make_key("query", "tenant_a", "abc123") == "graphrag:query:tenant_a:abc123"

    def test_none_tenant(self):
        assert make_key("schema", None) == "graphrag:schema:_"

    def test_single_part(self):
        assert make_key("entities") == "graphrag:entities"


class TestHashQuestion:
    def test_deterministic(self):
        h1 = hash_question("hello world")
        h2 = hash_question("hello world")
        assert h1 == h2

    def test_different(self):
        h1 = hash_question("question A")
        h2 = hash_question("question B")
        assert h1 != h2

    def test_length(self):
        h = hash_question("test")
        assert len(h) == 16


class TestInMemoryCache:
    def test_get_set(self):
        c = InMemoryCache()
        c.set("k1", {"a": 1})
        assert c.get("k1") == {"a": 1}

    def test_get_missing(self):
        c = InMemoryCache()
        assert c.get("nonexistent") is None

    def test_ttl_expiry(self):
        c = InMemoryCache()
        c.set("k1", "val", ttl=1)
        assert c.get("k1") == "val"
        time.sleep(1.1)
        assert c.get("k1") is None

    def test_no_ttl_persists(self):
        c = InMemoryCache()
        c.set("k1", "val", ttl=0)
        assert c.get("k1") == "val"

    def test_lru_eviction(self):
        c = InMemoryCache(max_size=3)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.set("d", 4)  # evicts "a"
        assert c.get("a") is None
        assert c.get("b") == 2

    def test_delete(self):
        c = InMemoryCache()
        c.set("k1", "val")
        c.delete("k1")
        assert c.get("k1") is None

    def test_delete_prefix(self):
        c = InMemoryCache()
        c.set("graphrag:query:t1:a", 1)
        c.set("graphrag:query:t1:b", 2)
        c.set("graphrag:query:t2:c", 3)
        c.set("graphrag:schema:t1", 4)
        removed = c.delete_prefix("graphrag:query:t1:")
        assert removed == 2
        assert c.get("graphrag:query:t1:a") is None
        assert c.get("graphrag:query:t2:c") == 3
        assert c.get("graphrag:schema:t1") == 4

    def test_clear(self):
        c = InMemoryCache()
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        assert c.get("a") is None
        assert c.get("b") is None

    def test_lru_access_refreshes(self):
        c = InMemoryCache(max_size=3)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        # Access "a" to refresh it
        c.get("a")
        c.set("d", 4)  # evicts "b" (oldest untouched)
        assert c.get("a") == 1
        assert c.get("b") is None

    def test_overwrite(self):
        c = InMemoryCache()
        c.set("k", "v1")
        c.set("k", "v2")
        assert c.get("k") == "v2"


class TestCacheIntegration:
    """Test that the global cache singleton works."""

    def test_global_cache_exists(self):
        from app.cache import cache
        assert cache is not None

    def test_global_cache_set_get(self):
        from app.cache import cache
        cache.set("test:integration", {"x": 42}, ttl=10)
        assert cache.get("test:integration") == {"x": 42}
        cache.delete("test:integration")
