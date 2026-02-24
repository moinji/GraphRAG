"""Ontology generation endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import OntologyGenerateRequest, OntologyGenerateResponse
from app.ontology.pipeline import generate_ontology

router = APIRouter(prefix="/api/v1/ontology", tags=["ontology"])


@router.post("/generate", response_model=OntologyGenerateResponse)
def generate(request: OntologyGenerateRequest) -> OntologyGenerateResponse:
    """Generate an ontology from an ERD schema.

    Stage 1: FK rule engine (always runs)
    Stage 2: Claude LLM enrichment (skipped if skip_llm=true or no API key)
    """
    return generate_ontology(erd=request.erd, skip_llm=request.skip_llm)
