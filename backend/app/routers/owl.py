"""OWL export & SHACL validation API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.config import settings
from app.exceptions import OWLReasoningError, VersionNotFoundError
from app.models.schemas import OWLExportResponse, SHACLValidationResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/owl", tags=["owl"])


@router.get("/export/{version_id}", response_model=OWLExportResponse)
def export_owl(
    version_id: int,
    fmt: str = Query("turtle", description="turtle | xml | json-ld"),
) -> OWLExportResponse:
    """Approved 온톨로지를 OWL 형식으로 내보내기."""
    if not settings.enable_owl:
        raise OWLReasoningError("OWL 기능이 비활성화 상태입니다 (ENABLE_OWL=true 필요)")

    from app.db.pg_client import get_version
    from app.owl.converter import ontology_to_owl, serialize_owl
    from app.models.schemas import OntologySpec

    row = get_version(version_id)
    if row is None:
        raise VersionNotFoundError(version_id)

    ontology = OntologySpec(**row["ontology_json"])
    # ontology_versions 테이블에 detected_domain 없음 → None 전달
    owl_graph = ontology_to_owl(ontology, domain=None)
    content = serialize_owl(owl_graph, fmt=fmt)

    from rdflib.namespace import OWL as OWL_NS, RDF
    class_count = sum(1 for _ in owl_graph.subjects(RDF.type, OWL_NS.Class))
    prop_count = sum(1 for _ in owl_graph.subjects(RDF.type, OWL_NS.ObjectProperty))

    return OWLExportResponse(
        content=content,
        format=fmt,
        triple_count=len(owl_graph),
        class_count=class_count,
        property_count=prop_count,
    )


@router.post("/validate/{version_id}", response_model=SHACLValidationResponse)
def validate_owl(version_id: int) -> SHACLValidationResponse:
    """온톨로지에 대해 SHACL 검증 실행 (TBox-level consistency check)."""
    if not settings.enable_owl:
        raise OWLReasoningError("OWL 기능이 비활성화 상태입니다 (ENABLE_OWL=true 필요)")

    from app.db.pg_client import get_version
    from app.models.schemas import OntologySpec
    from app.owl.converter import ontology_to_owl
    from app.owl.shacl_generator import generate_shapes
    from app.owl.shacl_validator import validate_shacl

    row = get_version(version_id)
    if row is None:
        raise VersionNotFoundError(version_id)

    ontology = OntologySpec(**row["ontology_json"])
    owl_graph = ontology_to_owl(ontology)
    shapes_graph = generate_shapes(ontology)
    conforms, issues = validate_shacl(owl_graph, shapes_graph)

    return SHACLValidationResponse(
        conforms=conforms,
        issue_count=len(issues),
        issues=[{"severity": i.severity, "message": i.message, "details": i.details} for i in issues],
        level="tbox",
    )
