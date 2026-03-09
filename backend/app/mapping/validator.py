"""YAML mapping validation — structural integrity checks."""

from __future__ import annotations

import logging

from app.mapping.models import DomainMappingConfig

logger = logging.getLogger(__name__)


def validate_mapping(config: DomainMappingConfig) -> list[str]:
    """Validate a DomainMappingConfig for structural integrity.

    Returns a list of error/warning messages. Empty list = valid.
    """
    errors: list[str] = []

    tm_ids = {tm.id for tm in config.triples_maps}

    # ── 1. Duplicate TriplesMap IDs ──
    seen_tm: set[str] = set()
    for tm in config.triples_maps:
        if tm.id in seen_tm:
            errors.append(f"Duplicate TriplesMap ID: {tm.id}")
        seen_tm.add(tm.id)

    # ── 2. Duplicate RelationshipMap IDs ──
    seen_rm: set[str] = set()
    for rm in config.relationship_maps:
        if rm.id in seen_rm:
            errors.append(f"Duplicate RelationshipMap ID: {rm.id}")
        seen_rm.add(rm.id)

    # ── 3. RelationshipMap references valid TriplesMap ──
    for rm in config.relationship_maps:
        if rm.source_triples_map not in tm_ids:
            errors.append(
                f"RelationshipMap '{rm.id}' references non-existent "
                f"source_triples_map '{rm.source_triples_map}'"
            )
        if rm.target_triples_map not in tm_ids:
            errors.append(
                f"RelationshipMap '{rm.id}' references non-existent "
                f"target_triples_map '{rm.target_triples_map}'"
            )

    # ── 4. Each TriplesMap has at least one is_key property ──
    for tm in config.triples_maps:
        has_key = any(p.is_key for p in tm.properties)
        if not has_key and tm.properties:
            errors.append(
                f"TriplesMap '{tm.id}' has no is_key property — "
                f"first property will be used as key"
            )

    # ── 5. Datatype references are valid ──
    if config.type_mappings:
        valid_types = set(config.type_mappings.keys())
        for tm in config.triples_maps:
            for p in tm.properties:
                if p.datatype not in valid_types:
                    errors.append(
                        f"TriplesMap '{tm.id}' property '{p.name}' has "
                        f"unknown datatype '{p.datatype}'"
                    )
        for rm in config.relationship_maps:
            for p in rm.properties:
                if p.datatype not in valid_types:
                    errors.append(
                        f"RelationshipMap '{rm.id}' property '{p.name}' has "
                        f"unknown datatype '{p.datatype}'"
                    )

    if errors:
        logger.warning("Mapping validation: %d issue(s) found", len(errors))
    return errors
