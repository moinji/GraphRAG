"""E2E tests for hybrid search pipeline (Mode C).

Tests the full flow: document upload → vector search → KG enrichment → answer.
All external services (PG, Neo4j, LLM) are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def _app():
    return create_app()


@pytest.fixture
async def api_client(_app):
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── Document Upload E2E ──────────────────────────────────────

class TestDocumentUploadE2E:
    @pytest.mark.anyio
    @patch("app.document.pipeline.vector_store")
    @patch("app.document.pipeline.embed_texts", return_value=[[0.1] * 1536])
    @patch("app.document.linker.link_document_to_kg")
    async def test_upload_txt_document(
        self, mock_linker, mock_embed, mock_vs, api_client,
    ):
        """Upload a text document and verify it's queued for processing."""
        mock_vs.insert_document.return_value = 1
        mock_vs.upsert_chunks.return_value = 1
        mock_vs.update_document_status.return_value = True

        from app.document.linker import LinkingResult
        mock_linker.return_value = LinkingResult(
            document_id=1, document_node_created=True,
            chunk_nodes_created=1, mentions_created=0,
        )

        import io
        files = [("files", ("test.txt", io.BytesIO(b"Sample document text for testing."), "text/plain"))]
        resp = await api_client.post("/api/v1/documents/upload", files=files)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_queued"] >= 1

    @pytest.mark.anyio
    @patch("app.db.vector_store.list_documents", return_value=[])
    async def test_list_documents_empty(self, mock_list, api_client):
        resp = await api_client.get("/api/v1/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


# ── Mode C Query E2E ─────────────────────────────────────────

class TestModeCQueryE2E:
    @pytest.mark.anyio
    @patch("app.query.hybrid_search.run_hybrid_query")
    async def test_mode_c_query(self, mock_hybrid, api_client):
        """Mode C query returns hybrid answer with document sources."""
        from app.models.schemas import DocumentSource, QueryResponse

        mock_hybrid.return_value = QueryResponse(
            question="맥북프로 배터리?",
            answer="맥북프로의 배터리는 최대 22시간입니다.",
            cypher="",
            paths=["[문서: macbook.pdf]"],
            template_id="hybrid_search",
            route="hybrid",
            matched_by="hybrid_c",
            mode="c",
            latency_ms=150,
            document_sources=[
                DocumentSource(
                    document_id=1,
                    filename="macbook.pdf",
                    chunk_text="맥북프로 M3는 최대 22시간의 배터리...",
                    relevance_score=0.89,
                    page_num=3,
                    chunk_index=2,
                ),
            ],
        )

        resp = await api_client.post(
            "/api/v1/query",
            json={"question": "맥북프로 배터리?", "mode": "c"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "c"
        assert data["matched_by"] == "hybrid_c"
        assert len(data["document_sources"]) == 1
        assert data["document_sources"][0]["filename"] == "macbook.pdf"
        assert "배터리" in data["answer"]

    @pytest.mark.anyio
    @patch("app.query.hybrid_search.run_hybrid_query")
    async def test_mode_c_no_results(self, mock_hybrid, api_client):
        """Mode C with no documents returns graceful message."""
        from app.models.schemas import QueryResponse

        mock_hybrid.return_value = QueryResponse(
            question="알 수 없는 질문",
            answer="관련 문서나 그래프 데이터를 찾을 수 없습니다.",
            cypher="",
            paths=[],
            template_id="hybrid_search",
            route="hybrid",
            matched_by="hybrid_c",
            mode="c",
            error="No relevant context found",
            latency_ms=50,
            document_sources=[],
        )

        resp = await api_client.post(
            "/api/v1/query",
            json={"question": "알 수 없는 질문", "mode": "c"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is not None
        assert data["document_sources"] == []


# ── Reranking E2E ────────────────────────────────────────────

class TestRerankingE2E:
    @pytest.mark.anyio
    @patch("app.query.reranker.settings")
    @patch("app.query.hybrid_search.search_documents")
    @patch("app.query.hybrid_search._get_kg_context", return_value="")
    @patch("app.query.hybrid_search._generate_hybrid_answer")
    async def test_reranker_integrated(
        self, mock_gen, mock_kg, mock_search, mock_settings, api_client,
    ):
        """Reranker runs between vector search and KG enrichment."""
        mock_settings.openai_api_key = None  # no LLM reranking

        mock_search.return_value = [
            {"text": "날씨 정보", "score": 0.9, "document_id": 1, "filename": "a.txt", "metadata": {}},
            {"text": "맥북프로 배터리 수명", "score": 0.5, "document_id": 2, "filename": "b.txt", "metadata": {}},
        ]

        mock_gen.return_value = ("맥북프로 배터리는 22시간", ["[문서: b.txt]"], 100)

        from app.query.hybrid_search import run_hybrid_query
        result = run_hybrid_query("맥북프로 배터리")

        assert result.mode == "c"
        assert result.answer is not None


# ── Document-KG Linking E2E ──────────────────────────────────

class TestDocumentKGLinkingE2E:
    @pytest.mark.anyio
    @patch("app.document.pipeline.vector_store")
    @patch("app.document.pipeline.embed_texts", return_value=[[0.1] * 1536])
    @patch("app.document.linker.link_document_to_kg")
    async def test_pipeline_calls_linker(
        self, mock_linker, mock_embed, mock_vs,
    ):
        """Document pipeline calls linker after storing chunks."""
        mock_vs.insert_document.return_value = 1
        mock_vs.upsert_chunks.return_value = 1
        mock_vs.update_document_status.return_value = True

        from app.document.linker import LinkingResult
        mock_linker.return_value = LinkingResult(
            document_id=1, document_node_created=True,
            chunk_nodes_created=1, mentions_created=2,
        )

        from app.document.pipeline import process_document
        result = process_document("test.txt", b"Alice ordered a MacBook Pro")

        assert result.status == "ready"
        mock_linker.assert_called_once()

    @pytest.mark.anyio
    @patch("app.document.pipeline.vector_store")
    @patch("app.document.pipeline.embed_texts", return_value=[[0.1] * 1536])
    @patch("app.document.linker.link_document_to_kg", side_effect=Exception("Neo4j down"))
    async def test_linker_failure_non_fatal(
        self, mock_linker, mock_embed, mock_vs,
    ):
        """Linker failure doesn't block document processing."""
        mock_vs.insert_document.return_value = 2
        mock_vs.upsert_chunks.return_value = 1
        mock_vs.update_document_status.return_value = True

        from app.document.pipeline import process_document
        result = process_document("test.txt", b"Some content for testing")

        assert result.status == "ready"  # still succeeds


# ── Evaluation API E2E ───────────────────────────────────────

class TestEvaluationE2E:
    @pytest.mark.anyio
    async def test_get_unstructured_golden(self, api_client):
        """GET /golden/unstructured returns 15 pairs."""
        resp = await api_client.get("/api/v1/evaluation/golden/unstructured")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 15

    @pytest.mark.anyio
    @patch("app.evaluation.qa_evaluator.run_evaluation_c")
    async def test_run_c_evaluation(self, mock_eval_c, api_client):
        """POST /run-c returns Mode C evaluation results."""
        from app.models.schemas import QASingleResult
        mock_eval_c.return_value = [
            QASingleResult(
                qa_id="U-D01", mode="c", question="test",
                answer="test answer", keyword_score=0.8,
                entity_score=1.0, latency_ms=100, success=True,
            ),
        ]

        resp = await api_client.post("/api/v1/evaluation/run-c")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["mode"] == "c"
