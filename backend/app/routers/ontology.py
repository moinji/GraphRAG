"""Ontology generation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.schemas import OntologyGenerateRequest, OntologyGenerateResponse
from app.ontology.pipeline import generate_ontology
from app.tenant import get_tenant_id

router = APIRouter(prefix="/api/v1/ontology", tags=["ontology"])


@router.post("/generate", response_model=OntologyGenerateResponse)
def generate(body: OntologyGenerateRequest, request: Request) -> OntologyGenerateResponse:
    """Generate an ontology from an ERD schema.

    Stage 1: FK rule engine (always runs)
    Stage 2: Claude LLM enrichment (skipped if skip_llm=true or no API key)
    """
    tenant_id = get_tenant_id(request)
    return generate_ontology(erd=body.erd, skip_llm=body.skip_llm, tenant_id=tenant_id)
