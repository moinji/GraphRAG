"""Tests for embedding service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.document.embedder import embed_single, embed_texts, get_embedding_dimension


class TestEmbeddingDimension:
    def test_default_dimension(self):
        dim = get_embedding_dimension()
        assert dim == 1536

    def test_dimension_is_positive(self):
        assert get_embedding_dimension() > 0


class TestEmbedTexts:
    def test_empty_input(self):
        assert embed_texts([]) == []

    @patch("app.document.embedder.settings")
    def test_no_api_key_returns_zero_vectors(self, mock_settings):
        """When no API key and no local model, return zero vectors."""
        mock_settings.openai_api_key = None

        # Mock local model import to fail
        with patch("app.document.embedder._embed_local", side_effect=ImportError("no model")):
            result = embed_texts(["hello"])

        assert len(result) == 1
        assert len(result[0]) == 1536
        assert all(v == 0.0 for v in result[0])

    @patch("app.document.embedder.settings")
    def test_openai_embed_called_when_key_present(self, mock_settings):
        """When OpenAI key is present, use OpenAI embedding."""
        mock_settings.openai_api_key = "test-key"
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_batch_size = 100

        fake_embedding = [0.1] * 1536

        with patch("app.document.embedder._embed_openai", return_value=[fake_embedding]) as mock_fn:
            result = embed_texts(["hello world"])

        assert len(result) == 1
        assert result[0] == fake_embedding
        mock_fn.assert_called_once_with(["hello world"])

    @patch("app.document.embedder.settings")
    def test_openai_failure_falls_back(self, mock_settings):
        """When OpenAI fails, fall back to local or zero vectors."""
        mock_settings.openai_api_key = "test-key"
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_batch_size = 100

        with patch("app.document.embedder._embed_openai", side_effect=Exception("API error")):
            with patch("app.document.embedder._embed_local", side_effect=ImportError("no model")):
                result = embed_texts(["hello"])

        assert len(result) == 1
        # Should be zero vectors as last resort
        assert len(result[0]) == 1536

    @patch("app.document.embedder.settings")
    def test_batch_processing(self, mock_settings):
        """Multiple texts should all get embeddings."""
        mock_settings.openai_api_key = None

        with patch("app.document.embedder._embed_local", side_effect=ImportError("no model")):
            result = embed_texts(["text1", "text2", "text3"])

        assert len(result) == 3


class TestEmbedSingle:
    @patch("app.document.embedder.settings")
    def test_single_text(self, mock_settings):
        mock_settings.openai_api_key = None

        with patch("app.document.embedder._embed_local", side_effect=ImportError("no model")):
            result = embed_single("hello")

        assert len(result) == 1536
