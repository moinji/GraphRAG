"""Neo4j singleton drivers — sync + async shared connection pools.

Sync driver: ``get_driver()`` — used by existing pipeline code.
Async driver: ``get_async_driver()`` / ``async_execute_query()`` — for new async paths.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncGraphDatabase, GraphDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_driver = None
_async_driver = None


def get_driver():
    """Return the singleton sync Neo4j driver, creating it on first call."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        logger.info("Neo4j driver created for %s", settings.neo4j_uri)
    return _driver


def get_async_driver():
    """Return the singleton async Neo4j driver, creating it on first call."""
    global _async_driver
    if _async_driver is None:
        _async_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        logger.info("Neo4j async driver created for %s", settings.neo4j_uri)
    return _async_driver


async def async_execute_query(
    cypher: str,
    params: dict[str, Any] | None = None,
    *,
    database: str | None = None,
) -> list[dict[str, Any]]:
    """Execute a Cypher query using the async driver and return records as dicts."""
    driver = get_async_driver()
    async with driver.session(database=database) as session:
        result = await session.run(cypher, params or {})
        records = await result.data()
        return records


def close_driver() -> None:
    """Close the singleton drivers (call on app shutdown)."""
    global _driver, _async_driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("Neo4j sync driver closed")
    # Async driver close is best-effort (may need event loop)
    if _async_driver is not None:
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_async_driver.close())
            else:
                loop.run_until_complete(_async_driver.close())
        except Exception:
            logger.debug("Async driver close skipped (no event loop)", exc_info=True)
        _async_driver = None
        logger.info("Neo4j async driver closed")
