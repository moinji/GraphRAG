"""Wisdom API — POST /api/v1/wisdom/query."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.schemas import WisdomRequest, WisdomResponse
from app.query.wisdom_engine import run_wisdom_query
from app.tenant import get_tenant_id

router = APIRouter(prefix="/api/v1/wisdom", tags=["wisdom"])


@router.post("/query", response_model=WisdomResponse)
def wisdom_query(req: WisdomRequest, request: Request) -> WisdomResponse:
    """Execute a DIKW Wisdom analysis query."""
    tenant_id = get_tenant_id(request)
    return run_wisdom_query(req.question, tenant_id=tenant_id)
