"""Tests for query reranker module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.query.reranker import _keyword_rerank, _parse_llm_scores, rerank


def _make_result(text: str, score: float = 0.5) -> dict:
    return {"text": text, "score": score, "document_id": 1, "filename": "test.pdf"}


# ── _keyword_rerank ───────────────────────────────────────────

class TestKeywordRerank:
    def test_empty_results(self):
        assert _keyword_rerank("질문", []) == []

    def test_keyword_boost(self):
        results = [
            _make_result("맥북프로는 훌륭한 노트북입니다.", 0.8),
            _make_result("오늘 날씨가 좋습니다.", 0.9),
        ]
        scored = _keyword_rerank("맥북프로 노트북", results)
        # The result mentioning 맥북프로 and 노트북 should get higher rerank_score
        assert scored[0]["rerank_score"] > scored[1]["rerank_score"]

    def test_english_keywords(self):
        results = [
            _make_result("MacBook Pro has great battery life.", 0.7),
            _make_result("The weather is nice today.", 0.8),
        ]
        scored = _keyword_rerank("MacBook battery", results)
        assert scored[0]["rerank_score"] > scored[1]["rerank_score"]

    def test_no_keywords_uses_vector_score(self):
        results = [_make_result("text", 0.6)]
        scored = _keyword_rerank("a", results)  # single char → no usable keywords
        assert scored[0]["rerank_score"] == pytest.approx(0.6, abs=0.01)

    def test_combined_score_formula(self):
        results = [_make_result("맥북 배터리", 0.8)]
        scored = _keyword_rerank("맥북 배터리", results)
        # 70% vector (0.8) + 30% keyword (1.0) = 0.56 + 0.30 = 0.86
        assert scored[0]["rerank_score"] == pytest.approx(0.86, abs=0.01)

    def test_partial_keyword_match(self):
        results = [_make_result("맥북프로 사양", 0.5)]
        scored = _keyword_rerank("맥북프로 배터리 수명", results)
        # 1 out of 3 keywords match → keyword_ratio = 0.333
        # 0.5 * 0.7 + 0.333 * 0.3 ≈ 0.45
        assert scored[0]["rerank_score"] == pytest.approx(0.45, abs=0.02)


# ── _parse_llm_scores ────────────────────────────────────────

class TestParseLlmScores:
    def test_valid_array(self):
        assert _parse_llm_scores("[8, 5, 3]", 3) == [8.0, 5.0, 3.0]

    def test_with_surrounding_text(self):
        assert _parse_llm_scores("Scores: [7, 4, 9]\nDone.", 3) == [7.0, 4.0, 9.0]

    def test_empty(self):
        assert _parse_llm_scores("", 3) == []

    def test_no_array(self):
        assert _parse_llm_scores("no scores here", 3) == []

    def test_truncates_to_expected(self):
        result = _parse_llm_scores("[8, 5, 3, 7, 2]", 3)
        assert len(result) == 3


# ── rerank (integration) ─────────────────────────────────────

class TestRerank:
    def test_empty_input(self):
        assert rerank("question", []) == []

    def test_returns_top_k(self):
        results = [_make_result(f"text {i}", 0.5 + i * 0.01) for i in range(10)]
        reranked = rerank("text", results, top_k=3)
        assert len(reranked) == 3

    @patch("app.query.reranker.settings")
    def test_no_llm_uses_keyword_only(self, mock_settings):
        mock_settings.openai_api_key = None
        results = [
            _make_result("맥북프로 배터리", 0.5),
            _make_result("날씨 정보", 0.9),
        ]
        reranked = rerank("맥북프로", results, top_k=2)
        # keyword match should boost first result despite lower vector score
        assert reranked[0]["text"] == "맥북프로 배터리"

    def test_preserves_original_fields(self):
        results = [_make_result("test text", 0.7)]
        results[0]["document_id"] = 42
        reranked = rerank("test", results)
        assert reranked[0]["document_id"] == 42

    def test_sorted_descending(self):
        results = [
            _make_result("no match", 0.3),
            _make_result("맥북프로 배터리 수명 테스트", 0.7),
        ]
        reranked = rerank("맥북프로 배터리", results)
        assert reranked[0]["rerank_score"] >= reranked[-1]["rerank_score"]
