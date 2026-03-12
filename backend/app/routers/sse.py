"""SSE (Server-Sent Events) streaming endpoints.

- GET /api/v1/kg/build/{job_id}/stream  — KG build progress
- POST /api/v1/query/stream             — Q&A token streaming (mode b)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.exceptions import (
    BuildJobNotFoundError,
    CypherExecutionError,
    LocalSearchError,
    QueryRoutingError,
)
from app.kg_builder.service import get_job
from app.models.schemas import QueryRequest
from app.tenant import get_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["sse"])


# ── KG Build SSE ─────────────────────────────────────────────────


async def _kg_build_event_generator(
    job_id: str, tenant_id: str | None, request: Request,
) -> AsyncGenerator[dict, None]:
    """Yield SSE events for KG build progress until terminal state."""
    last_json = ""
    while True:
        if await request.is_disconnected():
            break

        job = get_job(job_id, tenant_id=tenant_id)
        if job is None:
            yield {"event": "error", "data": json.dumps({"detail": f"Job {job_id} not found"})}
            return

        current_json = job.model_dump_json()
        if current_json != last_json:
            last_json = current_json
            if job.status in ("succeeded", "failed"):
                yield {"event": "done", "data": current_json}
                return
            yield {"event": "progress", "data": current_json}

        await asyncio.sleep(0.5)


@router.get("/kg/build/{job_id}/stream")
async def stream_kg_build(job_id: str, request: Request) -> EventSourceResponse:
    """Stream KG build progress via SSE (replaces polling)."""
    tenant_id = get_tenant_id(request)
    job = get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise BuildJobNotFoundError(job_id)

    return EventSourceResponse(
        _kg_build_event_generator(job_id, tenant_id, request),
        headers={"X-Accel-Buffering": "no"},
    )


# ── Query SSE ────────────────────────────────────────────────────


async def _query_stream_generator(
    question: str, mode: str, tenant_id: str | None, request: Request,
) -> AsyncGenerator[dict, None]:
    """Yield SSE events for Q&A query.

    Mode "a": fast template-based → single 'complete' event.
    Mode "b": LLM streaming → 'metadata' + 'token'* + 'complete' events.
    """
    if mode == "a":
        # Mode "a": streaming template pipeline (metadata → complete)
        from app.query.pipeline import run_query_stream

        try:
            for event in await asyncio.to_thread(
                lambda: list(run_query_stream(question, tenant_id=tenant_id)),
            ):
                if await request.is_disconnected():
                    return
                event_type = event.pop("_event", "complete")
                yield {"event": event_type, "data": json.dumps(event, ensure_ascii=False)}
        except CypherExecutionError as e:
            yield {"event": "error", "data": json.dumps({"detail": e.detail})}
        except Exception as e:
            logger.error("Mode A stream error: %s", e, exc_info=True)
            yield {"event": "error", "data": json.dumps({"detail": str(e)})}
        return

    if mode not in ("b",):
        # Mode "c" / "w" / other: run synchronously and return single event
        from app.query.pipeline import run_query
        result = await asyncio.to_thread(run_query, question, mode=mode, tenant_id=tenant_id)
        yield {"event": "complete", "data": result.model_dump_json()}
        return

    # Mode "b": streaming local search
    try:
        from app.query.local_search import run_local_query_stream
        async for event in run_local_query_stream(question, tenant_id=tenant_id):
            if await request.is_disconnected():
                return
            event_type = event.pop("_event", "token")
            yield {"event": event_type, "data": json.dumps(event, ensure_ascii=False)}
    except LocalSearchError as e:
        logger.warning("Local search stream error: %s", e)
        yield {"event": "error", "data": json.dumps({"detail": e.detail})}
    except CypherExecutionError as e:
        logger.warning("Cypher execution stream error: %s", e)
        yield {"event": "error", "data": json.dumps({"detail": e.detail})}
    except Exception as e:
        logger.error("Unexpected query stream error: %s", e, exc_info=True)
        yield {"event": "error", "data": json.dumps({"detail": str(e)})}


@router.post("/query/stream")
async def stream_query(req: QueryRequest, request: Request) -> EventSourceResponse:
    """Stream Q&A response via SSE (token-by-token for mode b)."""
    question = req.question.strip()
    if not question:
        raise QueryRoutingError("Question cannot be empty")
    mode = req.mode if req.mode in ("a", "b", "c", "w") else "a"
    tenant_id = get_tenant_id(request)

    return EventSourceResponse(
        _query_stream_generator(question, mode, tenant_id, request),
        headers={"X-Accel-Buffering": "no"},
    )
