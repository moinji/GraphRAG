"""Neo4j singleton driver — shared connection pool across the application."""

from __future__ import annotations

import logging

from neo4j import GraphDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_driver = None


def get_driver():
    """Return the singleton Neo4j driver, creating it on first call."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        logger.info("Neo4j driver created for %s", settings.neo4j_uri)
    return _driver


def close_driver() -> None:
    """Close the singleton driver (call on app shutdown)."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")
