"""Query API endpoint: POST /api/v1/query."""

from __future__ import annotations

from fastapi import APIRouter

from app.exceptions import QueryRoutingError
from app.models.schemas import QueryRequest, QueryResponse
from app.query.pipeline import run_query

router = APIRouter(prefix="/api/v1/query", tags=["query"])


@router.post("", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    """Run a natural-language question through the hybrid query pipeline."""
    question = req.question.strip()
    if not question:
        raise QueryRoutingError("Question cannot be empty")
    mode = req.mode if req.mode in ("a", "b") else "a"
    return run_query(question, mode=mode)
