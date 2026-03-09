"""OntologySpec → DomainMappingConfig (YAML) generator.

Converts the internal OntologySpec representation to a declarative
YAML mapping configuration with R2RML-compatible structure.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import yaml

from app.mapping.models import (
    DomainMappingConfig,
    JoinCondition,
    LogicalTable,
    MappingMetadata,
    MappingProperty,
    RelationshipMapEntry,
    SubjectMap,
    TriplesMapEntry,
    TypeMapping,
)
from app.models.schemas import OntologySpec

logger = logging.getLogger(__name__)

# Default type mappings for Phase 1
_DEFAULT_TYPE_MAPPINGS: dict[str, TypeMapping] = {
    "integer": TypeMapping(neo4j_type="Integer", python_type="int"),
    "float": TypeMapping(neo4j_type="Float", python_type="float"),
    "string": TypeMapping(neo4j_type="String", python_type="str"),
    "boolean": TypeMapping(neo4j_type="Boolean", python_type="bool"),
}


def _triples_map_id(class_name: str) -> str:
    """Generate a TriplesMap ID from node class name."""
    return f"TM_{class_name}"


def _relationship_map_id(rel_type: str) -> str:
    """Generate a RelationshipMap ID from relationship type."""
    return f"RM_{rel_type}"


def ontology_to_mapping(
    ontology: OntologySpec,
    domain: str | None = None,
    version_id: int | None = None,
) -> DomainMappingConfig:
    """Convert OntologySpec to DomainMappingConfig.

    Every field in OntologySpec is preserved — no information loss.
    """
    metadata = MappingMetadata(
        domain=domain,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_ontology_version=version_id,
    )

    # Build node→TriplesMap ID lookup
    node_to_tm_id: dict[str, str] = {}

    # ── TriplesMap entries (node types) ──
    triples_maps: list[TriplesMapEntry] = []
    for nt in ontology.node_types:
        tm_id = _triples_map_id(nt.name)
        node_to_tm_id[nt.name] = tm_id

        # Find key property for template
        key_prop = "id"
        for p in nt.properties:
            if p.is_key:
                key_prop = p.name
                break

        props = [
            MappingProperty(
                name=p.name,
                column=p.source_column,
                datatype=p.type,
                is_key=p.is_key,
            )
            for p in nt.properties
        ]

        triples_maps.append(TriplesMapEntry(
            id=tm_id,
            logical_table=LogicalTable(table_name=nt.source_table),
            subject_map=SubjectMap(class_=nt.name, template=f"{{{key_prop}}}"),
            properties=props,
        ))

    # ── RelationshipMap entries ──
    relationship_maps: list[RelationshipMapEntry] = []
    # Track relationship name occurrences for dedup
    rel_id_counter: dict[str, int] = {}

    for rt in ontology.relationship_types:
        # Generate unique ID (handle duplicate relationship names)
        base_id = _relationship_map_id(rt.name)
        if base_id in rel_id_counter:
            rel_id_counter[base_id] += 1
            rm_id = f"{base_id}_{rel_id_counter[base_id]}"
        else:
            rel_id_counter[base_id] = 0
            rm_id = base_id

        src_tm = node_to_tm_id.get(rt.source_node, f"TM_{rt.source_node}")
        tgt_tm = node_to_tm_id.get(rt.target_node, f"TM_{rt.target_node}")

        props = [
            MappingProperty(
                name=p.name,
                column=p.source_column,
                datatype=p.type,
            )
            for p in rt.properties
        ]

        relationship_maps.append(RelationshipMapEntry(
            id=rm_id,
            type=rt.name,
            source_triples_map=src_tm,
            target_triples_map=tgt_tm,
            logical_table=LogicalTable(table_name=rt.data_table),
            join_condition=JoinCondition(
                source_column=rt.source_key_column,
                target_column=rt.target_key_column,
            ),
            derivation=rt.derivation,
            properties=props,
        ))

    return DomainMappingConfig(
        version="1.0",
        metadata=metadata,
        triples_maps=triples_maps,
        relationship_maps=relationship_maps,
        type_mappings=_DEFAULT_TYPE_MAPPINGS,
    )


def mapping_to_yaml(config: DomainMappingConfig) -> str:
    """Serialize DomainMappingConfig to YAML string."""
    data = config.model_dump()
    return yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


def yaml_to_mapping(yaml_str: str) -> DomainMappingConfig:
    """Deserialize YAML string to DomainMappingConfig.

    Pydantic validates the structure automatically.
    """
    data = yaml.safe_load(yaml_str)
    return DomainMappingConfig.model_validate(data)
