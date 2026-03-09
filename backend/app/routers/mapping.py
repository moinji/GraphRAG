"""YAML mapping endpoints — generate, retrieve, update, preview."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.db.pg_client import get_version
from app.exceptions import MappingValidationError, VersionNotFoundError
from app.mapping.converter import mapping_to_ontology
from app.mapping.generator import mapping_to_yaml, ontology_to_mapping, yaml_to_mapping
from app.mapping.validator import validate_mapping
from app.models.schemas import (
    MappingGenerateRequest,
    MappingGenerateResponse,
    MappingPreview,
    OntologySpec,
)
from app.tenant import get_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mapping", tags=["mapping"])

# In-memory mapping store: version_id → yaml_str
_mapping_store: dict[int, str] = {}


@router.post("/generate", response_model=MappingGenerateResponse)
def generate_mapping(body: MappingGenerateRequest, request: Request) -> MappingGenerateResponse:
    """Generate YAML mapping from an approved ontology version."""
    tenant_id = get_tenant_id(request)
    version_row = get_version(body.version_id, tenant_id=tenant_id)
    if version_row is None:
        raise VersionNotFoundError(body.version_id)

    ontology = OntologySpec(**version_row["ontology_json"])
    domain = version_row.get("domain")

    # Generate mapping config
    config = ontology_to_mapping(ontology, domain=domain, version_id=body.version_id)

    # Validate
    warnings = validate_mapping(config)

    # Serialize to YAML
    yaml_content = mapping_to_yaml(config)

    # Store in memory
    _mapping_store[body.version_id] = yaml_content

    return MappingGenerateResponse(
        yaml_content=yaml_content,
        triples_map_count=len(config.triples_maps),
        relationship_map_count=len(config.relationship_maps),
        validation_warnings=warnings,
        version_id=body.version_id,
    )


@router.get("/{version_id}", response_model=MappingGenerateResponse)
def get_mapping(version_id: int, request: Request) -> MappingGenerateResponse:
    """Retrieve stored YAML mapping for a version."""
    tenant_id = get_tenant_id(request)

    yaml_content = _mapping_store.get(version_id)
    if yaml_content is None:
        # Auto-generate if not stored yet
        version_row = get_version(version_id, tenant_id=tenant_id)
        if version_row is None:
            raise VersionNotFoundError(version_id)

        ontology = OntologySpec(**version_row["ontology_json"])
        config = ontology_to_mapping(ontology, version_id=version_id)
        yaml_content = mapping_to_yaml(config)
        _mapping_store[version_id] = yaml_content

    config = yaml_to_mapping(yaml_content)
    warnings = validate_mapping(config)

    return MappingGenerateResponse(
        yaml_content=yaml_content,
        triples_map_count=len(config.triples_maps),
        relationship_map_count=len(config.relationship_maps),
        validation_warnings=warnings,
        version_id=version_id,
    )


@router.put("/{version_id}", response_model=MappingGenerateResponse)
def update_mapping(version_id: int, body: dict, request: Request) -> MappingGenerateResponse:
    """Upload modified YAML mapping. Validates before storing."""
    yaml_content = body.get("yaml_content", "")
    if not yaml_content:
        raise MappingValidationError("yaml_content is required")

    # Parse and validate
    try:
        config = yaml_to_mapping(yaml_content)
    except Exception as e:
        raise MappingValidationError(f"Invalid YAML: {e}")

    errors = validate_mapping(config)
    validation_errors = [e for e in errors if "non-existent" in e or "Duplicate" in e]
    if validation_errors:
        raise MappingValidationError("Mapping validation failed", errors=validation_errors)

    # Store
    _mapping_store[version_id] = yaml_content

    return MappingGenerateResponse(
        yaml_content=yaml_content,
        triples_map_count=len(config.triples_maps),
        relationship_map_count=len(config.relationship_maps),
        validation_warnings=[e for e in errors if e not in validation_errors],
        version_id=version_id,
    )


@router.get("/{version_id}/preview", response_model=MappingPreview)
def get_mapping_preview(version_id: int, request: Request) -> MappingPreview:
    """Get a summary of the YAML mapping for UI display."""
    tenant_id = get_tenant_id(request)

    yaml_content = _mapping_store.get(version_id)
    if yaml_content is None:
        version_row = get_version(version_id, tenant_id=tenant_id)
        if version_row is None:
            raise VersionNotFoundError(version_id)

        ontology = OntologySpec(**version_row["ontology_json"])
        config = ontology_to_mapping(ontology, version_id=version_id)
    else:
        config = yaml_to_mapping(yaml_content)

    table_mappings = [
        {
            "table": tm.logical_table.table_name,
            "node_label": tm.subject_map.class_,
            "property_count": len(tm.properties),
        }
        for tm in config.triples_maps
    ]

    return MappingPreview(
        version_id=version_id,
        node_count=len(config.triples_maps),
        relationship_count=len(config.relationship_maps),
        table_mappings=table_mappings,
        domain=config.metadata.domain,
    )
