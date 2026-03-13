"""Query API endpoints: single + batch + history + analytics."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from fastapi import APIRouter, Query, Request

from app.exceptions import QueryRoutingError
from app.models.schemas import (
    BatchQueryRequest,
    BatchQueryResponse,
    QueryRequest,
    QueryResponse,
)
from app.query.pipeline import run_query
from app.tenant import get_tenant_id

router = APIRouter(prefix="/api/v1/query", tags=["query"])

_BATCH_MAX = 20
_BATCH_POOL = ThreadPoolExecutor(max_workers=5)


@router.post("", response_model=QueryResponse)
def query(req: QueryRequest, request: Request) -> QueryResponse:
    """Run a natural-language question through the hybrid query pipeline."""
    tenant_id = get_tenant_id(request)
    question = req.question.strip()
    if not question:
        raise QueryRoutingError("Question cannot be empty")
    mode = req.mode if req.mode in ("a", "b", "c", "d") else "a"
    return run_query(question, mode=mode, tenant_id=tenant_id)


@router.post("/batch", response_model=BatchQueryResponse)
def batch_query(req: BatchQueryRequest, request: Request) -> BatchQueryResponse:
    """Run multiple questions in parallel (max 20)."""
    tenant_id = get_tenant_id(request)

    if not req.questions:
        raise QueryRoutingError("At least one question required")
    if len(req.questions) > _BATCH_MAX:
        raise QueryRoutingError(f"Maximum {_BATCH_MAX} questions per batch")

    t0 = time.time()
    results: list[QueryResponse] = [None] * len(req.questions)  # type: ignore[list-item]

    def _run(idx: int, q: QueryRequest) -> tuple[int, QueryResponse]:
        question = q.question.strip()
        if not question:
            return idx, QueryResponse(
                question="", answer="", cypher="", error="Empty question",
            )
        mode = q.mode if q.mode in ("a", "b", "c", "d") else "a"
        try:
            return idx, run_query(question, mode=mode, tenant_id=tenant_id)
        except Exception as e:
            return idx, QueryResponse(
                question=question, answer="", cypher="", error=str(e), mode=mode,
            )

    max_workers = min(req.max_parallel, 5, len(req.questions))
    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for i, q in enumerate(req.questions):
            futures.append(pool.submit(_run, i, q))
        for future in as_completed(futures):
            idx, resp = future.result()
            results[idx] = resp

    latency_ms = int((time.time() - t0) * 1000)
    return BatchQueryResponse(
        results=results, total=len(results), latency_ms=latency_ms,
    )


@router.get("/history")
def query_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Return recent query history for the tenant."""
    from app.db.query_log import get_query_history

    tenant_id = get_tenant_id(request)
    rows = get_query_history(tenant_id, limit=limit, offset=offset)
    return {"history": rows, "count": len(rows)}


@router.get("/analytics")
def query_analytics(request: Request) -> dict[str, Any]:
    """Return aggregated query analytics for the tenant."""
    from app.db.query_log import get_query_analytics

    tenant_id = get_tenant_id(request)
    return get_query_analytics(tenant_id)
