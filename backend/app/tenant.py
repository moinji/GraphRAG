"""Multi-tenancy utilities.

Single-tenant mode: tenant_id is None, no label prefix, backward compatible.
Multi-tenant mode: tenant_id from API key, Neo4j labels prefixed with t_{id}_.
"""

from __future__ import annotations

import json
import logging

from fastapi import Request

logger = logging.getLogger(__name__)

DEFAULT_TENANT_DB = "_default_"


def get_tenant_id(request: Request) -> str | None:
    """Extract tenant_id from request state (set by auth middleware)."""
    return getattr(request.state, "tenant_id", None)


def tenant_db_id(tenant_id: str | None) -> str:
    """Return the tenant identifier for DB storage (never None)."""
    return tenant_id or DEFAULT_TENANT_DB


def tenant_label_prefix(tenant_id: str | None) -> str:
    """Return the Neo4j label prefix for a tenant.

    Returns empty string in single-tenant mode (no prefix).
    """
    if tenant_id is None:
        return ""
    return f"t_{tenant_id}_"


def prefixed_label(tenant_id: str | None, label: str) -> str:
    """Apply tenant prefix to a Neo4j label."""
    return f"{tenant_label_prefix(tenant_id)}{label}"


def prefix_cypher_labels(
    cypher: str,
    tenant_id: str | None,
    known_labels: list[str],
) -> str:
    """Replace known bare labels in Cypher with tenant-prefixed versions.

    Matches patterns like :Customer, (n:Customer), -[:REL_TYPE]->
    Only replaces node labels (after : in parentheses), not relationship types.
    """
    if tenant_id is None:
        return cypher
    prefix = tenant_label_prefix(tenant_id)
    result = cypher
    # Sort by length desc to avoid partial replacements (e.g., "Order" before "OrderItem")
    for label in sorted(known_labels, key=len, reverse=True):
        # Replace `:Label` patterns in node contexts (inside parentheses or after MATCH)
        # Pattern: `:Label` followed by space, ), {, or end
        import re
        result = re.sub(
            rf"([(:]){re.escape(label)}(\s|[){{]|$)",
            rf"\g<1>{prefix}{label}\2",
            result,
        )
    return result


def get_tenant_map() -> dict[str, str]:
    """Parse TENANT_KEYS setting into {api_key: tenant_id} dict."""
    from app.config import settings
    if not settings.tenant_keys:
        return {}
    try:
        return json.loads(settings.tenant_keys)
    except (json.JSONDecodeError, TypeError):
        logger.error("Invalid TENANT_KEYS format (expected JSON object)")
        return {}
