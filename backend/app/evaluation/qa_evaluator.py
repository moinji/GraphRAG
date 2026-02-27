"""QA evaluation engine: A/B comparison with keyword/entity scoring."""

from __future__ import annotations

import logging
import time

from app.models.schemas import (
    QAComparisonReport,
    QAGoldenPair,
    QASingleResult,
    QueryResponse,
)

logger = logging.getLogger(__name__)

# Sonnet input/output price per 1M tokens (USD)
_INPUT_PRICE_PER_M = 3.0
_OUTPUT_PRICE_PER_M = 15.0
# Rough estimate: 70% input, 30% output
_BLENDED_PRICE_PER_M = _INPUT_PRICE_PER_M * 0.7 + _OUTPUT_PRICE_PER_M * 0.3


def evaluate_single(pair: QAGoldenPair, response: QueryResponse) -> QASingleResult:
    """Evaluate a single QA pair against the actual response.

    Scoring:
    - keyword_score: fraction of expected_keywords found in answer
    - entity_score: fraction of expected_entities found in answer
    - unsupported: success if error field is set or answer contains "지원"
    """
    answer_lower = response.answer.lower() if response.answer else ""

    # Unsupported category: success if properly rejected
    if pair.category == "unsupported":
        is_rejected = (
            response.error is not None
            or "지원" in answer_lower
            or "찾을 수 없" in answer_lower
            or "unsupported" in answer_lower
        )
        return QASingleResult(
            qa_id=pair.id,
            mode=response.mode,
            question=pair.question,
            answer=response.answer,
            keyword_score=1.0 if is_rejected else 0.0,
            entity_score=1.0 if is_rejected else 0.0,
            latency_ms=response.latency_ms or 0,
            llm_tokens=response.llm_tokens_used or 0,
            success=is_rejected,
        )

    # Normal categories: keyword + entity matching
    keyword_score = 0.0
    if pair.expected_keywords:
        matched = sum(1 for kw in pair.expected_keywords if kw.lower() in answer_lower)
        keyword_score = matched / len(pair.expected_keywords)

    entity_score = 0.0
    if pair.expected_entities:
        matched = sum(1 for ent in pair.expected_entities if ent.lower() in answer_lower)
        entity_score = matched / len(pair.expected_entities)
    else:
        entity_score = 1.0  # no entities expected → perfect

    # Success: at least one keyword matched (or no keywords expected)
    success = keyword_score > 0 if pair.expected_keywords else True
    # Also fail if there's an error response for non-unsupported
    if response.error and pair.category != "unsupported":
        success = False

    return QASingleResult(
        qa_id=pair.id,
        mode=response.mode,
        question=pair.question,
        answer=response.answer,
        keyword_score=keyword_score,
        entity_score=entity_score,
        latency_ms=response.latency_ms or 0,
        llm_tokens=response.llm_tokens_used or 0,
        success=success,
    )


def run_evaluation_a(
    pairs: list[QAGoldenPair],
    query_fn=None,
) -> list[QASingleResult]:
    """Run all pairs through A안 pipeline. Uses mock if query_fn provided."""
    if query_fn is None:
        from app.query.pipeline import run_query
        query_fn = lambda q: run_query(q, mode="a")

    results: list[QASingleResult] = []
    for pair in pairs:
        try:
            response = query_fn(pair.question)
            result = evaluate_single(pair, response)
        except Exception as e:
            logger.warning("A안 evaluation failed for %s: %s", pair.id, e)
            result = QASingleResult(
                qa_id=pair.id,
                mode="a",
                question=pair.question,
                answer="",
                keyword_score=0.0,
                entity_score=0.0,
                latency_ms=0,
                success=False,
                error=str(e),
            )
        results.append(result)
    return results


def run_evaluation_b(
    pairs: list[QAGoldenPair],
    query_fn=None,
) -> list[QASingleResult]:
    """Run all pairs through B안 pipeline. Uses mock if query_fn provided."""
    if query_fn is None:
        from app.query.pipeline import run_query
        query_fn = lambda q: run_query(q, mode="b")

    results: list[QASingleResult] = []
    for pair in pairs:
        try:
            response = query_fn(pair.question)
            result = evaluate_single(pair, response)
        except Exception as e:
            logger.warning("B안 evaluation failed for %s: %s", pair.id, e)
            result = QASingleResult(
                qa_id=pair.id,
                mode="b",
                question=pair.question,
                answer="",
                keyword_score=0.0,
                entity_score=0.0,
                latency_ms=0,
                success=False,
                error=str(e),
            )
        results.append(result)
    return results


def build_comparison(
    a_results: list[QASingleResult],
    b_results: list[QASingleResult],
) -> QAComparisonReport:
    """Build A/B comparison report from evaluation results."""
    total = max(len(a_results), len(b_results))

    a_success = sum(1 for r in a_results if r.success)
    b_success = sum(1 for r in b_results if r.success)

    a_avg_latency = (
        sum(r.latency_ms for r in a_results) / len(a_results)
        if a_results else 0.0
    )
    b_avg_latency = (
        sum(r.latency_ms for r in b_results) / len(b_results)
        if b_results else 0.0
    )

    a_avg_kw = (
        sum(r.keyword_score for r in a_results) / len(a_results)
        if a_results else 0.0
    )
    b_avg_kw = (
        sum(r.keyword_score for r in b_results) / len(b_results)
        if b_results else 0.0
    )

    b_total_tokens = sum(r.llm_tokens for r in b_results)
    b_cost = b_total_tokens * _BLENDED_PRICE_PER_M / 1_000_000

    # Recommendation logic
    if a_success > b_success:
        recommendation = "a_only"
    elif b_success > a_success:
        recommendation = "b_preferred"
    elif b_avg_kw > a_avg_kw:
        recommendation = "b_preferred"
    elif a_avg_kw > b_avg_kw:
        recommendation = "a_only"
    else:
        recommendation = "hybrid"

    return QAComparisonReport(
        total_pairs=total,
        a_results=a_results,
        b_results=b_results,
        a_success_count=a_success,
        b_success_count=b_success,
        a_avg_latency_ms=round(a_avg_latency, 1),
        b_avg_latency_ms=round(b_avg_latency, 1),
        a_avg_keyword_score=round(a_avg_kw, 3),
        b_avg_keyword_score=round(b_avg_kw, 3),
        b_total_tokens=b_total_tokens,
        b_estimated_cost_usd=round(b_cost, 4),
        recommendation=recommendation,
    )
