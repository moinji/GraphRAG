"""Vector similarity search module for Mode C hybrid queries.

Wraps pgvector search with query embedding + result formatting.
"""

from __future__ import annotations

import logging

from app.db.vector_store import similarity_search
from app.document.embedder import embed_single

logger = logging.getLogger(__name__)


def search_documents(
    question: str,
    tenant_id: str | None = None,
    top_k: int = 10,
    score_threshold: float = 0.3,
) -> list[dict]:
    """Search documents by embedding similarity.

    Steps:
        1. Embed the question
        2. Search pgvector for similar chunks
        3. Filter by score threshold

    Returns list of {chunk_id, document_id, text, score, metadata, filename}.
    """
    # Step 1: Embed the question
    query_embedding = embed_single(question)

    # Check if we got a zero vector (no embedding backend available)
    if all(v == 0.0 for v in query_embedding):
        logger.warning("Zero vector from embedding — vector search will return no results")
        return []

    # Step 2: Search
    results = similarity_search(
        query_embedding=query_embedding,
        tenant_id=tenant_id,
        top_k=top_k,
        score_threshold=score_threshold,
    )

    logger.debug(
        "Vector search: %d results (threshold=%.2f) for question: %s",
        len(results), score_threshold, question[:50],
    )

    return results


def format_document_context(results: list[dict], max_chunks: int = 5) -> str:
    """Format vector search results into a text context for LLM.

    Returns a structured string with source references.
    """
    if not results:
        return ""

    lines: list[str] = []
    lines.append("[문서 검색 결과]")

    for i, result in enumerate(results[:max_chunks], 1):
        filename = result.get("filename", "unknown")
        score = result.get("score", 0.0)
        text = result.get("text", "")
        metadata = result.get("metadata", {})
        page_num = metadata.get("page_num")

        source_info = f"[출처: {filename}"
        if page_num:
            source_info += f", p.{page_num}"
        source_info += f", 관련도: {score:.2f}]"

        lines.append(f"\n--- 문서 {i} {source_info} ---")
        lines.append(text)

    return "\n".join(lines)
