"""Unified cache layer — Redis (optional) with in-memory fallback.

Usage::

    from app.cache import cache

    cache.set("key", {"data": 1}, ttl=300)
    val = cache.get("key")          # dict | None
    cache.delete("key")
    cache.delete_prefix("graphrag:query:tenant_a:")  # invalidate group
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


class InMemoryCache:
    """Thread-safe in-memory cache with LRU eviction and TTL."""

    def __init__(self, max_size: int = 512) -> None:
        self._lock = threading.Lock()
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at > 0 and time.time() > expires_at:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: int = 0) -> None:
        expires_at = (time.time() + ttl) if ttl > 0 else 0.0
        with self._lock:
            self._data[key] = (expires_at, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max_size:
                self._data.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                del self._data[k]
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class RedisCache:
    """Redis-backed cache with automatic JSON serialization."""

    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.from_url(url, decode_responses=True)
        # Verify connection
        self._client.ping()
        logger.info("Redis cache connected: %s", url.split("@")[-1] if "@" in url else url)

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.warning("Redis GET failed for key=%s", key, exc_info=True)
            return None

    def set(self, key: str, value: Any, ttl: int = 0) -> None:
        try:
            raw = json.dumps(value, ensure_ascii=False, default=str)
            if ttl > 0:
                self._client.setex(key, ttl, raw)
            else:
                self._client.set(key, raw)
        except Exception:
            logger.warning("Redis SET failed for key=%s", key, exc_info=True)

    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except Exception:
            logger.warning("Redis DELETE failed for key=%s", key, exc_info=True)

    def delete_prefix(self, prefix: str) -> int:
        """Delete all keys matching prefix* using SCAN (non-blocking)."""
        try:
            count = 0
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor, match=f"{prefix}*", count=100)
                if keys:
                    self._client.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception:
            logger.warning("Redis DELETE prefix failed: %s", prefix, exc_info=True)
            return 0

    def clear(self) -> None:
        try:
            self.delete_prefix("graphrag:")
        except Exception:
            logger.warning("Redis CLEAR failed", exc_info=True)


def _create_cache() -> InMemoryCache | RedisCache:
    """Create cache backend based on REDIS_URL config."""
    try:
        from app.config import settings

        if settings.redis_url:
            try:
                return RedisCache(settings.redis_url)
            except Exception:
                logger.warning(
                    "Redis connection failed, falling back to in-memory cache",
                    exc_info=True,
                )
    except Exception:
        pass
    return InMemoryCache()


# ── Helper for consistent cache keys ──────────────────────────────
def make_key(*parts: str | None) -> str:
    """Build a namespaced cache key: graphrag:{part1}:{part2}:..."""
    safe = [p if p is not None else "_" for p in parts]
    return "graphrag:" + ":".join(safe)


def hash_question(question: str) -> str:
    """Short hash for cache key (collision-resistant enough for cache)."""
    return hashlib.sha256(question.encode()).hexdigest()[:16]


# Global singleton — lazily created on first import
cache = _create_cache()
