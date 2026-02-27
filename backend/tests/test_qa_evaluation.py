"""QA evaluation tests — 10 cases."""

from __future__ import annotations

import pytest

from app.evaluation.qa_evaluator import build_comparison, evaluate_single
from app.evaluation.qa_golden import QA_GOLDEN_PAIRS
from app.models.schemas import QAGoldenPair, QASingleResult, QueryResponse


# ════════════════════════════════════════════════════════════════════
#  Golden Data Validation
# ════════════════════════════════════════════════════════════════════


def test_golden_pairs_count_50():
    """#1: Exactly 50 golden pairs."""
    assert len(QA_GOLDEN_PAIRS) == 50


def test_golden_pairs_all_categories():
    """#2: At least 4 distinct categories present."""
    categories = {p.category for p in QA_GOLDEN_PAIRS}
    assert len(categories) >= 4
    assert "traverse" in categories
    assert "aggregate" in categories
    assert "comparison" in categories
    assert "unsupported" in categories


def test_golden_pairs_have_keywords():
    """#3: Non-unsupported pairs have expected_keywords."""
    for pair in QA_GOLDEN_PAIRS:
        if pair.category != "unsupported":
            assert len(pair.expected_keywords) > 0, f"{pair.id} missing keywords"


# ════════════════════════════════════════════════════════════════════
#  Single Evaluation
# ════════════════════════════════════════════════════════════════════


def _make_pair(**kwargs) -> QAGoldenPair:
    defaults = {
        "id": "test",
        "question": "테스트",
        "category": "traverse",
        "expected_keywords": ["맥북프로", "에어팟프로"],
        "expected_entities": ["김민수"],
    }
    defaults.update(kwargs)
    return QAGoldenPair(**defaults)


def _make_response(answer: str, **kwargs) -> QueryResponse:
    defaults = {
        "question": "테스트",
        "answer": answer,
        "cypher": "",
        "mode": "a",
    }
    defaults.update(kwargs)
    return QueryResponse(**defaults)


def test_evaluate_perfect_answer():
    """#4: All keywords + entities matched → scores 1.0."""
    pair = _make_pair()
    resp = _make_response("김민수가 주문한 상품: 맥북프로, 에어팟프로")
    result = evaluate_single(pair, resp)
    assert result.keyword_score == 1.0
    assert result.entity_score == 1.0
    assert result.success is True


def test_evaluate_partial_answer():
    """#5: Half keywords matched → score 0.5."""
    pair = _make_pair()
    resp = _make_response("김민수가 주문한 상품: 맥북프로")
    result = evaluate_single(pair, resp)
    assert result.keyword_score == 0.5
    assert result.entity_score == 1.0
    assert result.success is True  # at least one keyword matched


def test_evaluate_wrong_answer():
    """#6: No match → scores 0.0."""
    pair = _make_pair()
    resp = _make_response("잘 모르겠습니다.")
    result = evaluate_single(pair, resp)
    assert result.keyword_score == 0.0
    assert result.entity_score == 0.0
    assert result.success is False


def test_evaluate_unsupported():
    """#7: Unsupported question with error → success."""
    pair = _make_pair(
        category="unsupported",
        expected_keywords=[],
        expected_entities=[],
    )
    resp = _make_response(
        "이 질문 유형은 아직 지원하지 않습니다.",
        error="No matching template found",
    )
    result = evaluate_single(pair, resp)
    assert result.success is True
    assert result.keyword_score == 1.0


# ════════════════════════════════════════════════════════════════════
#  Comparison Report
# ════════════════════════════════════════════════════════════════════


def _make_results(
    mode: str, success_count: int, total: int, latency: int = 50, tokens: int = 0
) -> list[QASingleResult]:
    results = []
    for i in range(total):
        results.append(QASingleResult(
            qa_id=f"Q{i}",
            mode=mode,
            question=f"질문 {i}",
            answer="답변",
            keyword_score=1.0 if i < success_count else 0.0,
            entity_score=1.0 if i < success_count else 0.0,
            latency_ms=latency,
            llm_tokens=tokens,
            success=i < success_count,
        ))
    return results


def test_comparison_report_fields():
    """#8: Report has all required fields."""
    a = _make_results("a", 8, 10, latency=30)
    b = _make_results("b", 7, 10, latency=200, tokens=500)
    report = build_comparison(a, b)
    assert report.total_pairs == 10
    assert report.a_success_count == 8
    assert report.b_success_count == 7
    assert report.a_avg_latency_ms > 0
    assert report.b_avg_latency_ms > 0
    assert report.a_avg_keyword_score > 0
    assert report.b_avg_keyword_score > 0
    assert report.b_total_tokens == 5000
    assert report.b_estimated_cost_usd >= 0


def test_recommendation_a_wins():
    """#9: A success > B success → recommendation 'a_only'."""
    a = _make_results("a", 8, 10)
    b = _make_results("b", 5, 10)
    report = build_comparison(a, b)
    assert report.recommendation == "a_only"


def test_cost_estimation():
    """#10: Token-based cost estimation is reasonable."""
    a = _make_results("a", 5, 10)
    b = _make_results("b", 5, 10, tokens=1000)
    report = build_comparison(a, b)
    # 10 * 1000 = 10000 tokens, blended rate ~7.6$/M
    assert report.b_total_tokens == 10000
    assert report.b_estimated_cost_usd > 0
    assert report.b_estimated_cost_usd < 1.0  # Should be small
