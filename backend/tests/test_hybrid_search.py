"""Tests for Mode C hybrid search pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.query.hybrid_search import (
    _build_document_sources,
    _generate_hybrid_answer,
    run_hybrid_query,
)
from app.query.hybrid_prompts import (
    build_hybrid_messages,
    parse_hybrid_answer,
)
from app.models.schemas import DocumentSource


class TestHybridPrompts:
    def test_build_messages_both_contexts(self):
        msgs = build_hybrid_messages("질문?", "문서 내용", "그래프 내용")
        assert len(msgs) == 1
        assert "문서 컨텍스트" in msgs[0]["content"]
        assert "그래프 컨텍스트" in msgs[0]["content"]

    def test_build_messages_doc_only(self):
        msgs = build_hybrid_messages("question?", "doc content", "")
        assert "문서 컨텍스트" in msgs[0]["content"]
        assert "그래프 컨텍스트" not in msgs[0]["content"]

    def test_build_messages_no_context(self):
        msgs = build_hybrid_messages("question?", "", "")
        assert "검색된 컨텍스트가 없습니다" in msgs[0]["content"]

    def test_parse_answer_with_sources(self):
        raw = "답변: 이것은 답변입니다.\n출처:\n- [그래프] Customer-PLACED->Order\n- [문서: report.pdf] 관련 내용"
        answer, sources = parse_hybrid_answer(raw)
        assert "이것은 답변입니다" in answer
        assert len(sources) == 2
        assert "[그래프]" in sources[0]
        assert "report.pdf" in sources[1]

    def test_parse_answer_no_sources(self):
        raw = "답변: 단순 답변입니다."
        answer, sources = parse_hybrid_answer(raw)
        assert "단순 답변" in answer
        assert sources == []

    def test_parse_answer_plain_text(self):
        raw = "Just a plain answer without format."
        answer, sources = parse_hybrid_answer(raw)
        assert answer == raw.strip()
        assert sources == []


class TestBuildDocumentSources:
    def test_empty(self):
        assert _build_document_sources([]) == []

    def test_single_result(self):
        results = [{
            "document_id": 1,
            "filename": "test.pdf",
            "text": "Some chunk text",
            "score": 0.85,
            "chunk_index": 2,
            "metadata": {"page_num": 3},
        }]

        sources = _build_document_sources(results)

        assert len(sources) == 1
        assert sources[0].document_id == 1
        assert sources[0].filename == "test.pdf"
        assert sources[0].relevance_score == 0.85
        assert sources[0].page_num == 3
        assert sources[0].chunk_index == 2

    def test_max_5_sources(self):
        results = [
            {"document_id": i, "filename": f"doc{i}.pdf", "text": "t", "score": 0.5,
             "chunk_index": 0, "metadata": {}}
            for i in range(10)
        ]

        sources = _build_document_sources(results)
        assert len(sources) == 5

    def test_truncates_long_text(self):
        results = [{
            "document_id": 1,
            "filename": "big.pdf",
            "text": "x" * 1000,
            "score": 0.9,
            "chunk_index": 0,
            "metadata": {},
        }]

        sources = _build_document_sources(results)
        assert len(sources[0].chunk_text) <= 500


class TestRunHybridQuery:
    @patch("app.query.hybrid_search._generate_hybrid_answer")
    @patch("app.query.hybrid_search._get_kg_context")
    @patch("app.query.hybrid_search.search_documents")
    def test_full_pipeline(self, mock_search, mock_kg, mock_llm):
        """Full Mode C pipeline with document and KG results."""
        mock_search.return_value = [{
            "chunk_id": 1, "document_id": 1, "text": "Document content",
            "score": 0.9, "chunk_index": 0, "metadata": {"page_num": 1},
            "filename": "test.pdf", "file_type": "pdf",
        }]
        mock_kg.return_value = "Customer(김민수):\n  -PLACED-> Order(ORD001)"
        mock_llm.return_value = ("답변 내용입니다.", ["[그래프] Customer->Order"], 500)

        result = run_hybrid_query("김민수의 주문은?")

        assert result.mode == "c"
        assert result.route == "hybrid"
        assert result.matched_by == "hybrid_c"
        assert "답변 내용" in result.answer
        assert len(result.document_sources) == 1
        assert result.document_sources[0].filename == "test.pdf"
        assert result.llm_tokens_used == 500

    @patch("app.query.hybrid_search._get_kg_context")
    @patch("app.query.hybrid_search.search_documents")
    def test_no_results_graceful(self, mock_search, mock_kg):
        """No vector results and no KG context returns graceful response."""
        mock_search.return_value = []
        mock_kg.return_value = ""

        result = run_hybrid_query("obscure question")

        assert result.mode == "c"
        assert result.error is not None
        assert result.document_sources == []

    @patch("app.query.hybrid_search._generate_hybrid_answer")
    @patch("app.query.hybrid_search._get_kg_context")
    @patch("app.query.hybrid_search.search_documents")
    def test_doc_only_no_kg(self, mock_search, mock_kg, mock_llm):
        """Documents found but no KG context."""
        mock_search.return_value = [{
            "chunk_id": 1, "document_id": 1, "text": "Doc text",
            "score": 0.8, "chunk_index": 0, "metadata": {},
            "filename": "notes.md", "file_type": "md",
        }]
        mock_kg.return_value = ""
        mock_llm.return_value = ("Answer from docs only.", [], 200)

        result = run_hybrid_query("What is in the notes?")

        assert result.mode == "c"
        assert result.answer == "Answer from docs only."
        assert len(result.document_sources) == 1

    @patch("app.query.hybrid_search._generate_hybrid_answer")
    @patch("app.query.hybrid_search._get_kg_context")
    @patch("app.query.hybrid_search.search_documents")
    def test_korean_question(self, mock_search, mock_kg, mock_llm):
        """Korean question with results."""
        mock_search.return_value = [{
            "chunk_id": 1, "document_id": 2, "text": "보고서 내용",
            "score": 0.95, "chunk_index": 0, "metadata": {"page_num": 5},
            "filename": "보고서.pdf", "file_type": "pdf",
        }]
        mock_kg.return_value = ""
        mock_llm.return_value = ("보고서에 따르면...", ["[문서: 보고서.pdf]"], 300)

        result = run_hybrid_query("보고서 내용은?")

        assert result.mode == "c"
        assert "보고서" in result.answer
        assert result.document_sources[0].page_num == 5

    @patch("app.query.hybrid_search._generate_hybrid_answer")
    @patch("app.query.hybrid_search._get_kg_context")
    @patch("app.query.hybrid_search.search_documents")
    def test_latency_tracking(self, mock_search, mock_kg, mock_llm):
        """Latency should be tracked."""
        mock_search.return_value = [{
            "chunk_id": 1, "document_id": 1, "text": "t",
            "score": 0.5, "chunk_index": 0, "metadata": {},
            "filename": "f.txt", "file_type": "txt",
        }]
        mock_kg.return_value = ""
        mock_llm.return_value = ("answer", [], 100)

        result = run_hybrid_query("question")

        assert result.latency_ms is not None
        assert result.latency_ms >= 0


class TestGenerateHybridAnswer:
    @patch("app.query.hybrid_search.settings")
    def test_no_llm_fallback(self, mock_settings):
        """No LLM keys returns raw context."""
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None

        answer, sources, tokens = _generate_hybrid_answer(
            "질문?", "문서 내용", "그래프 내용",
        )

        assert tokens == 0
        assert "문서 내용" in answer or "원본 컨텍스트" in answer

    @patch("app.query.hybrid_search.settings")
    def test_openai_success(self, mock_settings):
        """OpenAI LLM generates answer."""
        mock_settings.openai_api_key = "test-key"
        mock_settings.anthropic_api_key = None
        mock_settings.local_search_model = "gpt-4o"
        mock_settings.local_search_max_tokens = 2048

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "답변: 테스트 답변\n출처:\n- [문서: test.pdf]"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            with patch("app.llm_tracker.tracker"):
                answer, sources, tokens = _generate_hybrid_answer(
                    "질문?", "문서 내용", "그래프 내용",
                )

        assert "테스트 답변" in answer
        assert tokens == 150


class TestQueryAPIIntegration:
    """Test Mode C through the query API endpoint."""

    def test_mode_c_accepted(self):
        """POST /api/v1/query with mode=c is accepted."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)

        with patch("app.query.hybrid_search.run_hybrid_query") as mock_hybrid:
            from app.models.schemas import QueryResponse
            mock_hybrid.return_value = QueryResponse(
                question="test?",
                answer="hybrid answer",
                cypher="",
                mode="c",
                route="hybrid",
                matched_by="hybrid_c",
                template_id="hybrid_search",
                document_sources=[],
            )

            response = client.post(
                "/api/v1/query",
                json={"question": "test?", "mode": "c"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "c"
        assert data["answer"] == "hybrid answer"

    def test_mode_c_in_response_model(self):
        """QueryResponse includes document_sources field."""
        from app.models.schemas import QueryResponse, DocumentSource

        resp = QueryResponse(
            question="q",
            answer="a",
            cypher="",
            mode="c",
            document_sources=[
                DocumentSource(
                    document_id=1,
                    filename="test.pdf",
                    chunk_text="chunk",
                    relevance_score=0.9,
                ),
            ],
        )

        assert len(resp.document_sources) == 1
        assert resp.document_sources[0].filename == "test.pdf"
