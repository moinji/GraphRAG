"""Reranker for Mode C vector search results.

2-stage reranking following project pattern: rules first → LLM fallback.

Stage 1: Keyword/entity overlap scoring (deterministic, fast)
Stage 2: LLM cross-encoder reranking (optional, non-fatal)
"""

from __future__ import annotations

import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)

_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_STOPWORDS_KO = {"은", "는", "이", "가", "을", "를", "의", "에", "에서", "로", "으로", "와", "과", "도", "만", "까지", "부터", "에게", "한테"}
_STOPWORDS_EN = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "with", "and", "or", "but", "not", "this", "that", "it"}


def rerank(
    question: str,
    results: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """Rerank vector search results for better relevance.

    Stage 1: Keyword overlap boost (always runs)
    Stage 2: LLM cross-encoder (optional, non-fatal)

    Args:
        question: user question
        results: list of vector search result dicts
        top_k: max results to return after reranking

    Returns reranked list (top_k items), each dict has added 'rerank_score'.
    """
    if not results:
        return []

    # Stage 1: Keyword overlap scoring
    scored = _keyword_rerank(question, results)

    # Stage 2: LLM reranking (only if many results and API key available)
    if len(scored) > 3 and settings.openai_api_key:
        try:
            scored = _llm_rerank(question, scored, top_k)
        except Exception:
            logger.debug("LLM reranking failed (non-fatal)", exc_info=True)

    # Sort by combined score descending
    scored.sort(key=lambda r: r.get("rerank_score", 0), reverse=True)

    return scored[:top_k]


def _keyword_rerank(
    question: str,
    results: list[dict],
) -> list[dict]:
    """Stage 1: Boost results that share keywords with the question."""
    ko = bool(_HANGUL_RE.search(question))
    stopwords = _STOPWORDS_KO if ko else _STOPWORDS_EN

    # Extract question keywords
    q_tokens = set(
        t.lower()
        for t in re.findall(r"[\w가-힣]+", question)
        if len(t) > 1 and t.lower() not in stopwords
    )

    if not q_tokens:
        # No usable keywords — return with original scores
        for r in results:
            r["rerank_score"] = r.get("score", 0.0)
        return results

    for r in results:
        text = r.get("text", "")
        text_lower = text.lower()

        # Count keyword hits
        hits = sum(1 for t in q_tokens if t in text_lower)
        keyword_ratio = hits / len(q_tokens) if q_tokens else 0

        # Combined score: 70% vector similarity + 30% keyword overlap
        vector_score = r.get("score", 0.0)
        r["rerank_score"] = round(vector_score * 0.7 + keyword_ratio * 0.3, 4)

    return results


def _llm_rerank(
    question: str,
    results: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """Stage 2: LLM-based relevance scoring.

    Asks LLM to rate each chunk's relevance to the question (0-10).
    """
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)

    # Build compact prompt with chunk previews
    chunk_lines = []
    for i, r in enumerate(results[:10]):  # limit to top 10
        preview = r.get("text", "")[:200].replace("\n", " ")
        chunk_lines.append(f"[{i}] {preview}")

    prompt = (
        "Rate the relevance of each text chunk to the question on a scale of 0-10.\n"
        "Return ONLY a JSON array of scores, e.g. [8, 3, 7, ...]\n\n"
        f"Question: {question}\n\n"
        "Chunks:\n" + "\n".join(chunk_lines)
    )

    response = client.chat.completions.create(
        model=getattr(settings, "openai_router_model", "gpt-4o-mini"),
        max_tokens=200,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content or ""

    # Track usage
    try:
        from app.llm_tracker import tracker
        tracker.record(
            caller="reranker",
            model=getattr(settings, "openai_router_model", "gpt-4o-mini"),
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
    except Exception:
        pass

    # Parse scores
    scores = _parse_llm_scores(raw, len(results[:10]))

    # Apply LLM scores: blend with existing rerank_score
    for i, r in enumerate(results[:10]):
        if i < len(scores):
            llm_score = scores[i] / 10.0  # normalize to 0-1
            # 50% existing score + 50% LLM score
            r["rerank_score"] = round(r.get("rerank_score", 0) * 0.5 + llm_score * 0.5, 4)

    return results


def _parse_llm_scores(raw: str, expected_count: int) -> list[float]:
    """Parse LLM score response into a list of floats."""
    import json

    raw = raw.strip()
    match = re.search(r'\[[\d\s,\.]+\]', raw)
    if not match:
        return []

    try:
        scores = json.loads(match.group())
        return [float(s) for s in scores[:expected_count]]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
