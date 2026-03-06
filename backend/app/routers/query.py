"""Query API endpoint: POST /api/v1/query."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.exceptions import QueryRoutingError
from app.models.schemas import QueryRequest, QueryResponse
from app.query.pipeline import run_query
from app.tenant import get_tenant_id

router = APIRouter(prefix="/api/v1/query", tags=["query"])


@router.post("", response_model=QueryResponse)
def query(req: QueryRequest, request: Request) -> QueryResponse:
    """Run a natural-language question through the hybrid query pipeline."""
    tenant_id = get_tenant_id(request)
    question = req.question.strip()
    if not question:
        raise QueryRoutingError("Question cannot be empty")
    mode = req.mode if req.mode in ("a", "b") else "a"
    return run_query(question, mode=mode, tenant_id=tenant_id)
