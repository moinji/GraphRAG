"""Slot validation + Cypher generation.

Validates slot values to prevent Cypher injection, then renders the template.
"""

from __future__ import annotations

import re

from app.exceptions import QueryRoutingError
from app.query.template_registry import get_template, render_cypher

# Whitelist patterns for injection prevention
_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REL_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_OP_WHITELIST = {"=", "<>", ">", "<", ">=", "<=", "CONTAINS", "STARTS WITH", "ENDS WITH"}

# Slot names that hold node labels
_LABEL_SLOTS = {
    "start_label", "end_label", "mid_label",
    "mid1_label", "mid2_label", "label",
}

# Slot names that hold relationship types
_REL_SLOTS = {"rel1", "rel2", "rel3"}

# Slot names that hold property names
_PROP_SLOTS = {
    "start_prop", "end_prop", "return_prop",
    "group_prop", "filter_prop", "status_prop",
    "match_prop", "sort_prop",
}


def _validate_slot(name: str, value: str) -> None:
    """Validate a single slot value against injection rules."""
    if name in _LABEL_SLOTS:
        if not _LABEL_RE.match(value):
            raise QueryRoutingError(
                f"Invalid node label in slot '{name}': {value!r}"
            )
    elif name in _REL_SLOTS:
        if not _REL_RE.match(value):
            raise QueryRoutingError(
                f"Invalid relationship type in slot '{name}': {value!r}"
            )
    elif name in _PROP_SLOTS:
        if not _LABEL_RE.match(value):
            raise QueryRoutingError(
                f"Invalid property name in slot '{name}': {value!r}"
            )
    elif name == "op":
        if value not in _OP_WHITELIST:
            raise QueryRoutingError(
                f"Invalid operator in slot 'op': {value!r}"
            )
    elif name == "max_depth":
        if not value.isdigit() or int(value) < 1 or int(value) > 10:
            raise QueryRoutingError(
                f"Invalid max_depth: {value!r} (must be 1-10)"
            )


def fill_template(
    template_id: str,
    slots: dict[str, str],
    params: dict[str, object],
) -> tuple[str, dict[str, object]]:
    """Validate slots, render Cypher, return (cypher_string, neo4j_params).

    Raises:
        QueryRoutingError: If any slot value fails validation.
        KeyError: If template_id is not found.
    """
    spec = get_template(template_id)
    if spec is None:
        raise QueryRoutingError(f"Unknown template: {template_id}")

    # Validate all slot values
    for name, value in slots.items():
        _validate_slot(name, str(value))

    # Render Cypher with validated slots
    cypher = render_cypher(template_id, slots)

    # Filter params to only those expected by the template
    neo4j_params = {k: v for k, v in params.items() if k in spec.params}

    return cypher, neo4j_params
