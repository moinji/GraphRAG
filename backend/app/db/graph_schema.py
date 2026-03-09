"""Graph schema introspection — reads node labels, relationship types, and
properties from Neo4j.

Used by the LLM router and local search to build domain-agnostic prompts.
Cached with TTL to avoid repeated DB calls.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Schema cache keyed by tenant_id
_schema_cache: dict[str | None, dict] = {}
_schema_cache_ts: dict[str | None, float] = {}
_SCHEMA_CACHE_TTL = 300  # 5 minutes


def get_graph_schema(tenant_id: str | None = None) -> dict:
    """Return the current graph schema from Neo4j.

    Returns::

        {
            "node_labels": ["Customer", "Product", ...],
            "relationship_types": ["PLACED", "CONTAINS", ...],
            "node_properties": {"Customer": ["id", "name", "email"], ...},
            "relationship_properties": {"CONTAINS": ["quantity"], ...},
        }

    Returns empty lists/dicts on failure (non-fatal).
    """
    now = time.time()
    cached = _schema_cache.get(tenant_id)
    cached_ts = _schema_cache_ts.get(tenant_id, 0.0)
    if cached is not None and (now - cached_ts) < _SCHEMA_CACHE_TTL:
        return cached

    empty: dict = {
        "node_labels": [],
        "relationship_types": [],
        "node_properties": {},
        "relationship_properties": {},
    }

    try:
        from app.db.neo4j_client import get_driver
        from app.tenant import tenant_label_prefix

        driver = get_driver()
        prefix = tenant_label_prefix(tenant_id)
        schema: dict = {
            "node_labels": [],
            "relationship_types": [],
            "node_properties": {},
            "relationship_properties": {},
        }

        with driver.session() as session:
            # 1. Node labels
            result = session.run(
                "CALL db.labels() YIELD label RETURN label ORDER BY label"
            )
            raw_labels = [r["label"] for r in result]

            labels: list[str] = []
            for lbl in raw_labels:
                if prefix and lbl.startswith(prefix):
                    labels.append(lbl[len(prefix):])
                elif not prefix:
                    labels.append(lbl)
            schema["node_labels"] = labels

            # 2. Relationship types
            result = session.run(
                "CALL db.relationshipTypes() YIELD relationshipType "
                "RETURN relationshipType ORDER BY relationshipType"
            )
            schema["relationship_types"] = [r["relationshipType"] for r in result]

            # 3. Node properties (sample from first node of each label)
            for lbl in raw_labels:
                display = lbl[len(prefix):] if prefix and lbl.startswith(prefix) else lbl
                if display not in labels:
                    continue
                result = session.run(
                    f"MATCH (n:`{lbl}`) RETURN keys(n) AS props LIMIT 1"
                )
                for rec in result:
                    schema["node_properties"][display] = rec["props"]

            # 4. Relationship properties (sample from first rel of each type)
            for rel_type in schema["relationship_types"]:
                result = session.run(
                    f"MATCH ()-[r:`{rel_type}`]->() RETURN keys(r) AS props LIMIT 1"
                )
                for rec in result:
                    props = rec["props"]
                    if props:
                        schema["relationship_properties"][rel_type] = props

        if schema["node_labels"]:
            _schema_cache[tenant_id] = schema
            _schema_cache_ts[tenant_id] = now
            logger.debug(
                "Loaded graph schema: %d labels, %d rel types (tenant=%s)",
                len(schema["node_labels"]),
                len(schema["relationship_types"]),
                tenant_id,
            )
        return schema

    except Exception:
        logger.warning("Failed to load graph schema from Neo4j", exc_info=True)
        return empty


def invalidate_schema_cache(tenant_id: str | None = None) -> None:
    """Clear the schema cache (call after KG rebuild)."""
    if tenant_id is not None:
        _schema_cache.pop(tenant_id, None)
        _schema_cache_ts.pop(tenant_id, None)
    else:
        _schema_cache.clear()
        _schema_cache_ts.clear()


def format_schema_for_prompt(schema: dict) -> str:
    """Format graph schema as text for LLM prompts.

    Returns a concise multi-line summary of node types, relationships, and
    their properties. Returns a fallback message if schema is empty.
    """
    if not schema.get("node_labels"):
        return "No graph data loaded yet."

    lines: list[str] = []
    lines.append("Node types: " + ", ".join(schema["node_labels"]))
    lines.append("Relationships: " + ", ".join(schema["relationship_types"]))

    if schema.get("node_properties"):
        lines.append("\nNode properties:")
        for label, props in schema["node_properties"].items():
            lines.append(f"  {label}: {', '.join(props)}")

    if schema.get("relationship_properties"):
        lines.append("\nRelationship properties:")
        for rel_type, props in schema["relationship_properties"].items():
            lines.append(f"  {rel_type}: {', '.join(props)}")

    return "\n".join(lines)
