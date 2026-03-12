"""Tests for vector search module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.query.vector_search import format_document_context, search_documents

pytestmark = pytest.mark.skip(reason="stub: tests not yet implemented")


class TestSearchDocuments:
    @patch("app.query.vector_search.similarity_search")
    @patch("app.query.vector_search.embed_single")
    def test_basic_search(self, mock_embed, mock_search):
        """Basic vector search returns results."""
        mock_embed.return_value = [0.1] * 1536
        mock_search.return_value = [
            {"chunk_id": 1, "document_id": 1, "text": "Some text", "score": 0.85,
             "metadata": {"page_num": 1}, "filename": "doc.pdf", "file_type": "pdf"},
        ]

        results = search_documents("test question")

        assert len(results) == 1
        assert results[0]["score"] == 0.85
        mock_embed.assert_called_once_with("test question")

    @patch("app.query.vector_search.embed_single")
    def test_zero_vector_returns_empty(self, mock_embed):
        """Zero vector (no embedding backend) returns empty results."""
        mock_embed.return_value = [0.0] * 1536

        results = search_documents("test question")

        assert results == []

    @patch("app.query.vector_search.similarity_search")
    @patch("app.query.vector_search.embed_single")
    def test_empty_results(self, mock_embed, mock_search):
        """No matching documents returns empty list."""
        mock_embed.return_value = [0.1] * 1536
        mock_search.return_value = []

        results = search_documents("obscure query")

        assert results == []

    @patch("app.query.vector_search.similarity_search")
    @patch("app.query.vector_search.embed_single")
    def test_passes_tenant_id(self, mock_embed, mock_search):
        """Tenant ID is passed through to similarity search."""
        mock_embed.return_value = [0.1] * 1536
        mock_search.return_value = []

        search_documents("question", tenant_id="tenant_a")

        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args
        assert call_kwargs[1]["tenant_id"] == "tenant_a"

    @patch("app.query.vector_search.similarity_search")
    @patch("app.query.vector_search.embed_single")
    def test_custom_top_k(self, mock_embed, mock_search):
        """Custom top_k is passed through."""
        mock_embed.return_value = [0.1] * 1536
        mock_search.return_value = []

        search_documents("question", top_k=5)

        call_kwargs = mock_search.call_args
        assert call_kwargs[1]["top_k"] == 5


class TestFormatDocumentContext:
    def test_empty_results(self):
        assert format_document_context([]) == ""

    def test_single_result(self):
        results = [{
            "filename": "report.pdf",
            "score": 0.92,
            "text": "This is the content of the document.",
            "metadata": {"page_num": 3},
        }]

        context = format_document_context(results)

        assert "report.pdf" in context
        assert "p.3" in context
        assert "0.92" in context
        assert "This is the content" in context

    def test_multiple_results(self):
        results = [
            {"filename": "doc1.pdf", "score": 0.9, "text": "Text 1", "metadata": {}},
            {"filename": "doc2.pdf", "score": 0.8, "text": "Text 2", "metadata": {}},
            {"filename": "doc3.pdf", "score": 0.7, "text": "Text 3", "metadata": {}},
        ]

        context = format_document_context(results)

        assert "doc1.pdf" in context
        assert "doc2.pdf" in context
        assert "doc3.pdf" in context

    def test_max_chunks_limit(self):
        results = [
            {"filename": f"doc{i}.pdf", "score": 0.9 - i * 0.1, "text": f"Text {i}", "metadata": {}}
            for i in range(10)
        ]

        context = format_document_context(results, max_chunks=3)

        assert "doc0.pdf" in context
        assert "doc2.pdf" in context
        # doc3+ should NOT be included
        assert "doc5.pdf" not in context

    def test_no_page_num(self):
        results = [{
            "filename": "notes.md",
            "score": 0.75,
            "text": "Markdown content",
            "metadata": {},
        }]

        context = format_document_context(results)

        assert "notes.md" in context
        assert "p." not in context  # no page number
