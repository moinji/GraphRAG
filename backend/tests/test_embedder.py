"""Tests for embedding service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.document.embedder import embed_single, embed_texts, get_embedding_dimension


class TestEmbeddingDimension:
    def test_default_dimension(self):
        dim = get_embedding_dimension()
        # Without OpenAI key, falls back to local model dimension (384)
        assert dim in (384, 1536)

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
        dim = get_embedding_dimension()
        assert len(result[0]) == dim
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
        dim = get_embedding_dimension()
        assert len(result[0]) == dim

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

        dim = get_embedding_dimension()
        assert len(result) == dim


# ── Dimension detection tests ─────────────────────────────────────


class TestDimensionDetection:
    @patch("app.document.embedder.settings")
    @patch("app.document.embedder._openai_available", return_value=True)
    def test_openai_small_dimension(self, _mock_avail, mock_settings):
        mock_settings.openai_api_key = "test-key"
        mock_settings.embedding_model = "text-embedding-3-small"
        assert get_embedding_dimension() == 1536

    @patch("app.document.embedder.settings")
    @patch("app.document.embedder._openai_available", return_value=True)
    def test_openai_large_dimension(self, _mock_avail, mock_settings):
        mock_settings.openai_api_key = "test-key"
        mock_settings.embedding_model = "text-embedding-3-large"
        assert get_embedding_dimension() == 3072

    @patch("app.document.embedder.settings")
    @patch("app.document.embedder._openai_available", return_value=False)
    def test_openai_unavailable_falls_to_local(self, _mock_avail, mock_settings):
        mock_settings.openai_api_key = "test-key"
        mock_settings.local_embedding_model = "all-MiniLM-L6-v2"
        assert get_embedding_dimension() == 384

    @patch("app.document.embedder.settings")
    def test_no_key_uses_local(self, mock_settings):
        mock_settings.openai_api_key = None
        mock_settings.local_embedding_model = "all-mpnet-base-v2"
        assert get_embedding_dimension() == 768

    @patch("app.document.embedder.settings")
    def test_unknown_local_model_defaults_384(self, mock_settings):
        mock_settings.openai_api_key = None
        mock_settings.local_embedding_model = "unknown-model-xyz"
        assert get_embedding_dimension() == 384


class TestOpenAIAvailability:
    def test_cache_reset(self):
        """_openai_ok cache can be reset."""
        import app.document.embedder as emb
        original = emb._openai_ok
        emb._openai_ok = None  # reset
        try:
            with patch("app.document.embedder.settings") as mock_s:
                mock_s.openai_api_key = "fake"
                # Should fail and cache False
                result = emb._openai_available()
                assert result is False
                assert emb._openai_ok is False
        finally:
            emb._openai_ok = original

    def test_cached_result_reused(self):
        """Once cached, _openai_available returns cached value without API call."""
        import app.document.embedder as emb
        original = emb._openai_ok
        emb._openai_ok = True
        try:
            assert emb._openai_available() is True
        finally:
            emb._openai_ok = original


class TestLocalEmbedFallback:
    @patch("app.document.embedder.settings")
    def test_local_model_called_on_no_key(self, mock_settings):
        mock_settings.openai_api_key = None
        fake_vectors = [[0.5] * 384]

        with patch("app.document.embedder._embed_local", return_value=fake_vectors) as mock_local:
            result = embed_texts(["test text"])

        assert result == fake_vectors
        mock_local.assert_called_once()

    @patch("app.document.embedder.settings")
    def test_zero_vectors_have_correct_dim(self, mock_settings):
        mock_settings.openai_api_key = None
        mock_settings.local_embedding_model = "all-MiniLM-L6-v2"

        with patch("app.document.embedder._embed_local", side_effect=Exception("fail")):
            result = embed_texts(["hello", "world"])

        assert len(result) == 2
        assert len(result[0]) == 384  # local model dim
        assert len(result[1]) == 384
