"""YAML DomainMappingConfig → OntologySpec reverse converter.

Enables round-trip: OntologySpec → YAML → OntologySpec
"""

from __future__ import annotations

import logging

from app.mapping.models import DomainMappingConfig
from app.models.schemas import (
    NodeProperty,
    NodeType,
    OntologySpec,
    RelProperty,
    RelationshipType,
)

logger = logging.getLogger(__name__)


def mapping_to_ontology(config: DomainMappingConfig) -> OntologySpec:
    """Convert DomainMappingConfig back to OntologySpec.

    Resolves TriplesMap ID references to node class names.
    """
    # Build TriplesMap ID → class name lookup
    tm_id_to_class: dict[str, str] = {}
    for tm in config.triples_maps:
        tm_id_to_class[tm.id] = tm.subject_map.class_

    # ── Node types ──
    node_types: list[NodeType] = []
    for tm in config.triples_maps:
        props = [
            NodeProperty(
                name=p.name,
                source_column=p.column,
                type=p.datatype,
                is_key=p.is_key,
            )
            for p in tm.properties
        ]
        node_types.append(NodeType(
            name=tm.subject_map.class_,
            source_table=tm.logical_table.table_name,
            properties=props,
        ))

    # ── Relationship types ──
    relationship_types: list[RelationshipType] = []
    for rm in config.relationship_maps:
        source_node = tm_id_to_class.get(rm.source_triples_map, rm.source_triples_map)
        target_node = tm_id_to_class.get(rm.target_triples_map, rm.target_triples_map)

        props = [
            RelProperty(
                name=p.name,
                source_column=p.column,
                type=p.datatype,
            )
            for p in rm.properties
        ]

        relationship_types.append(RelationshipType(
            name=rm.type,
            source_node=source_node,
            target_node=target_node,
            data_table=rm.logical_table.table_name,
            source_key_column=rm.join_condition.source_column,
            target_key_column=rm.join_condition.target_column,
            properties=props,
            derivation=rm.derivation,
        ))

    return OntologySpec(
        node_types=node_types,
        relationship_types=relationship_types,
    )
