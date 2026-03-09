"""Tests for SSE streaming endpoints."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models.schemas import KGBuildResponse, KGBuildProgress

# SSE uses asyncio.sleep — restrict to asyncio backend only
pytestmark = pytest.mark.anyio


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── KG Build SSE ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_kg_build_stream_not_found(client: AsyncClient):
    """SSE stream returns 404 for non-existent job."""
    resp = await client.get("/api/v1/kg/build/nonexistent/stream")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_kg_build_stream_succeeded(client: AsyncClient):
    """SSE stream yields done event for already-completed job."""
    job = KGBuildResponse(
        build_job_id="test_123",
        status="succeeded",
        version_id=1,
        progress=KGBuildProgress(
            nodes_created=10, relationships_created=5,
            duration_seconds=1.0, current_step="completed",
            step_number=4, total_steps=4,
        ),
    )
    with patch("app.routers.sse.get_job", return_value=job):
        async with client.stream("GET", "/api/v1/kg/build/test_123/stream") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            events = []
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events.append(line.split("event: ")[1])
                elif line.startswith("data: ") and events:
                    data = json.loads(line[6:])
                    assert data["status"] == "succeeded"
                    break
            assert "done" in events


@pytest.mark.anyio
async def test_kg_build_stream_running_then_done(client: AsyncClient):
    """SSE stream yields progress then done events."""
    running_job = KGBuildResponse(
        build_job_id="test_456", status="running", version_id=1,
        progress=KGBuildProgress(
            current_step="neo4j_load", step_number=3, total_steps=4,
        ),
    )
    done_job = KGBuildResponse(
        build_job_id="test_456", status="succeeded", version_id=1,
        progress=KGBuildProgress(
            nodes_created=20, relationships_created=10,
            duration_seconds=2.5, current_step="completed",
            step_number=4, total_steps=4,
        ),
    )
    call_count = 0

    def mock_get_job(job_id, tenant_id=None):
        nonlocal call_count
        call_count += 1
        # call 1: route handler validation, call 2: first generator poll → running
        # call 3+: generator poll → done
        return running_job if call_count <= 2 else done_job

    with patch("app.routers.sse.get_job", side_effect=mock_get_job):
        async with client.stream("GET", "/api/v1/kg/build/test_456/stream") as resp:
            assert resp.status_code == 200
            events = []
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events.append(line.split("event: ")[1])
                if "done" in events:
                    break
            assert "progress" in events
            assert "done" in events


# ── Query SSE ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_query_stream_empty_question(client: AsyncClient):
    """Empty question returns 422."""
    resp = await client.post("/api/v1/query/stream", json={"question": "", "mode": "a"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_query_stream_mode_a(client: AsyncClient):
    """Mode A yields single complete event."""
    mock_result = MagicMock()
    mock_result.model_dump_json.return_value = json.dumps({
        "question": "test", "answer": "result", "cypher": "",
        "paths": [], "template_id": "", "route": "unsupported",
        "matched_by": "none", "error": None, "mode": "a",
        "subgraph_context": None, "llm_tokens_used": None,
        "latency_ms": 10, "cached": False, "related_node_ids": [],
    })

    with patch("app.routers.sse.asyncio") as mock_asyncio:
        # Mock asyncio.to_thread to return our mock result
        import asyncio as real_asyncio

        async def fake_to_thread(fn, *args, **kwargs):
            return mock_result

        mock_asyncio.to_thread = fake_to_thread
        mock_asyncio.sleep = real_asyncio.sleep

        async with client.stream("POST", "/api/v1/query/stream",
                                  json={"question": "test question", "mode": "a"}) as resp:
            assert resp.status_code == 200
            events = []
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events.append(line.split("event: ")[1])
                if "complete" in events:
                    break
            assert "complete" in events


@pytest.mark.anyio
async def test_query_stream_mode_b_unsupported(client: AsyncClient):
    """Mode B with unsupported question yields complete with error."""
    with patch("app.query.local_search._load_entities_from_neo4j", return_value={}):
        async with client.stream("POST", "/api/v1/query/stream",
                                  json={"question": "unknown question xyz", "mode": "b"}) as resp:
            assert resp.status_code == 200
            events = []
            last_data = None
            done = False
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events.append(line.split("event: ")[1])
                elif line.startswith("data: "):
                    last_data = json.loads(line[6:])
                    if events and events[-1] == "complete":
                        done = True
                        break
            assert "complete" in events
            assert last_data is not None
            assert last_data.get("route") == "unsupported"


@pytest.mark.anyio
async def test_query_stream_content_type(client: AsyncClient):
    """SSE response has correct content-type."""
    mock_result = MagicMock()
    mock_result.model_dump_json.return_value = json.dumps({
        "question": "test", "answer": "ok", "cypher": "",
        "paths": [], "template_id": "", "route": "unsupported",
        "matched_by": "none", "error": None, "mode": "a",
        "subgraph_context": None, "llm_tokens_used": None,
        "latency_ms": 5, "cached": False, "related_node_ids": [],
    })

    import asyncio as real_asyncio

    async def fake_to_thread(fn, *args, **kwargs):
        return mock_result

    with patch("app.routers.sse.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = fake_to_thread
        mock_asyncio.sleep = real_asyncio.sleep

        async with client.stream("POST", "/api/v1/query/stream",
                                  json={"question": "hello", "mode": "a"}) as resp:
            assert "text/event-stream" in resp.headers.get("content-type", "")
