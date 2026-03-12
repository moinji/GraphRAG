"""Embedding service: text -> vector.

Follows project pattern: primary (OpenAI) -> fallback (local sentence-transformers).
Graceful degradation: if no API key and no local model, returns empty vectors.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Default embedding dimension (OpenAI text-embedding-3-small)
DEFAULT_DIMENSION = 1536


def get_embedding_dimension() -> int:
    """Return the dimension of the configured embedding model.

    If OpenAI is unavailable (quota exceeded, no key), falls back to local model
    which uses a different dimension (384 for all-MiniLM-L6-v2).
    """
    # If OpenAI is available, use its dimension
    if settings.openai_api_key:
        model = getattr(settings, "embedding_model", "text-embedding-3-small")
        dim_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        # Check if OpenAI actually works (cache the result)
        if _openai_available():
            return dim_map.get(model, DEFAULT_DIMENSION)

    # Local model dimension
    local_dim_map = {
        "all-MiniLM-L6-v2": 384,
        "all-mpnet-base-v2": 768,
        "paraphrase-multilingual-MiniLM-L12-v2": 384,
    }
    local_model = getattr(settings, "local_embedding_model", "all-MiniLM-L6-v2")
    return local_dim_map.get(local_model, 384)


_openai_ok: bool | None = None


def _openai_available() -> bool:
    """Check if OpenAI embedding API is actually reachable (cached)."""
    global _openai_ok
    if _openai_ok is not None:
        return _openai_ok
    try:
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)
        client.embeddings.create(model="text-embedding-3-small", input=["test"])
        _openai_ok = True
    except Exception:
        _openai_ok = False
    return _openai_ok


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts into vectors.

    Strategy: OpenAI API -> local model fallback -> zero vectors.
    """
    if not texts:
        return []

    # Try OpenAI first
    if settings.openai_api_key:
        try:
            return _embed_openai(texts)
        except Exception as e:
            logger.warning("OpenAI embedding failed, trying fallback: %s", e)

    # Try local sentence-transformers
    try:
        return _embed_local(texts)
    except Exception as e:
        logger.warning("Local embedding also failed: %s", e)

    # Last resort: zero vectors (allows pipeline to continue)
    logger.error("No embedding backend available — returning zero vectors")
    dim = get_embedding_dimension()
    return [[0.0] * dim for _ in texts]


def embed_single(text: str) -> list[float]:
    """Embed a single text string."""
    results = embed_texts([text])
    return results[0] if results else [0.0] * get_embedding_dimension()


def _embed_openai(texts: list[str]) -> list[list[float]]:
    """Embed using OpenAI API (batch)."""
    import openai

    client = openai.OpenAI(api_key=settings.openai_api_key)
    model = getattr(settings, "embedding_model", "text-embedding-3-small")

    # OpenAI batch limit is 2048 texts
    batch_size = getattr(settings, "embedding_batch_size", 100)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        # Truncate very long texts to avoid token limits
        batch = [t[:8000] if len(t) > 8000 else t for t in batch]

        response = client.embeddings.create(
            model=model,
            input=batch,
        )
        # Sort by index to preserve order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        all_embeddings.extend([d.embedding for d in sorted_data])

    return all_embeddings


def _embed_local(texts: list[str]) -> list[list[float]]:
    """Embed using local sentence-transformers model."""
    from sentence_transformers import SentenceTransformer

    model_name = getattr(settings, "local_embedding_model", "all-MiniLM-L6-v2")
    model = _get_local_model(model_name)
    embeddings = model.encode(texts, show_progress_bar=False)
    return [e.tolist() for e in embeddings]


# Cache local model
_local_models: dict[str, Any] = {}


def _get_local_model(model_name: str) -> Any:
    """Get or load a local embedding model (cached)."""
    if model_name not in _local_models:
        from sentence_transformers import SentenceTransformer
        _local_models[model_name] = SentenceTransformer(model_name)
    return _local_models[model_name]
