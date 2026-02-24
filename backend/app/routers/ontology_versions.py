"""Ontology version management endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.db.pg_client import approve_version, get_version, update_version
from app.evaluation.evaluator import evaluate
from app.evaluation.golden_ecommerce import (
    GOLDEN_NODE_NAMES,
    GOLDEN_RELATIONSHIP_SPECS,
)
from app.exceptions import VersionConflictError, VersionNotFoundError
from app.models.schemas import (
    OntologyApproveResponse,
    OntologySpec,
    OntologyUpdateRequest,
    OntologyUpdateResponse,
    OntologyVersionResponse,
)

router = APIRouter(prefix="/api/v1/ontology/versions", tags=["ontology-versions"])


@router.get("/{version_id}", response_model=OntologyVersionResponse)
def get_ontology_version(version_id: int) -> OntologyVersionResponse:
    """Retrieve an ontology version by id."""
    row = get_version(version_id)
    if row is None:
        raise VersionNotFoundError(version_id)

    return OntologyVersionResponse(
        version_id=row["id"],
        erd_hash=row["erd_hash"],
        ontology=row["ontology_json"],
        eval_report=row.get("eval_json"),
        status=row.get("status", "draft"),
        created_at=str(row["created_at"]) if row.get("created_at") else None,
    )


@router.put("/{version_id}", response_model=OntologyUpdateResponse)
def update_ontology_version(
    version_id: int, body: OntologyUpdateRequest
) -> OntologyUpdateResponse:
    """Update ontology for a draft version. Re-calculates evaluation."""
    row = get_version(version_id)
    if row is None:
        raise VersionNotFoundError(version_id)

    if row.get("status") == "approved":
        raise VersionConflictError(
            f"Version {version_id} is already approved and cannot be modified"
        )

    # Re-calculate evaluation against golden data
    ontology = body.ontology
    eval_metrics = evaluate(ontology, GOLDEN_NODE_NAMES, GOLDEN_RELATIONSHIP_SPECS)

    ontology_dict = ontology.model_dump()
    eval_dict = eval_metrics.model_dump()

    updated = update_version(version_id, ontology_dict, eval_dict)

    return OntologyUpdateResponse(
        version_id=version_id,
        status="draft",
        updated=updated,
    )


@router.post("/{version_id}/approve", response_model=OntologyApproveResponse)
def approve_ontology_version(version_id: int) -> OntologyApproveResponse:
    """Approve a draft version (draft → approved)."""
    row = get_version(version_id)
    if row is None:
        raise VersionNotFoundError(version_id)

    if row.get("status") == "approved":
        raise VersionConflictError(f"Version {version_id} is already approved")

    approve_version(version_id)

    return OntologyApproveResponse(
        version_id=version_id,
        status="approved",
    )
