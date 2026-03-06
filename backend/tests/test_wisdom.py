"""Tests for the DIKW Wisdom layer."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.query.wisdom_router import WisdomIntent, classify_wisdom_intent


# ── Wisdom Router tests ──────────────────────────────────────────


class TestWisdomRouter:
    def test_pattern_intent(self):
        assert classify_wisdom_intent("고객 구매 패턴에서 어떤 트렌드가 보이나요?") == WisdomIntent.PATTERN

    def test_pattern_intent_analysis(self):
        assert classify_wisdom_intent("고객 세그먼트별 특징을 분석해줘") == WisdomIntent.PATTERN

    def test_causal_intent_why(self):
        assert classify_wisdom_intent("왜 전자기기 카테고리가 가장 많이 팔리나요?") == WisdomIntent.CAUSAL

    def test_causal_intent_correlation(self):
        assert classify_wisdom_intent("리뷰 평점과 판매량의 상관관계는?") == WisdomIntent.CAUSAL

    def test_recommendation_intent(self):
        assert classify_wisdom_intent("김민수에게 어떤 상품을 추천하면 좋을까요?") == WisdomIntent.RECOMMENDATION

    def test_recommendation_intent_improve(self):
        assert classify_wisdom_intent("공급사 관계를 강화해야 할 곳은?") == WisdomIntent.RECOMMENDATION

    def test_what_if_intent(self):
        assert classify_wisdom_intent("애플코리아 공급이 중단되면 어떤 영향이 있나요?") == WisdomIntent.WHAT_IF

    def test_what_if_intent_remove(self):
        assert classify_wisdom_intent("만약 노트북 카테고리를 제거하면?") == WisdomIntent.WHAT_IF

    def test_dikw_trace_intent(self):
        assert classify_wisdom_intent("김민수에 대한 DIKW 종합 분석을 해줘") == WisdomIntent.DIKW_TRACE

    def test_dikw_trace_intent_report(self):
        assert classify_wisdom_intent("전체 종합 보고서를 작성해줘") == WisdomIntent.DIKW_TRACE

    def test_lookup_fallback(self):
        assert classify_wisdom_intent("김민수가 주문한 상품은?") == WisdomIntent.LOOKUP

    def test_lookup_simple(self):
        assert classify_wisdom_intent("맥북프로 가격은?") == WisdomIntent.LOOKUP


# ── Wisdom Prompts tests ─────────────────────────────────────────


class TestWisdomPrompts:
    def test_serialize_collected_data(self):
        from app.query.wisdom_prompts import serialize_collected_data

        data = {
            "customer_segments": [
                {"customer": "김민수", "orders": 3, "total_spent": 7000000, "segment": "VIP"},
            ],
            "empty_query": [],
        }
        result = serialize_collected_data(data)
        assert "김민수" in result
        assert "VIP" in result
        assert "empty_query" not in result

    def test_build_wisdom_messages(self):
        from app.query.wisdom_prompts import build_wisdom_messages

        messages = build_wisdom_messages("테스트 질문", "pattern", "테스트 데이터")
        assert len(messages) == 1
        assert "pattern" in messages[0]["content"]
        assert "테스트 질문" in messages[0]["content"]


# ── Wisdom Collector tests ───────────────────────────────────────


class TestWisdomCollector:
    def test_intent_query_map_keys(self):
        from app.query.wisdom_collector import INTENT_QUERY_MAP, WISDOM_QUERIES

        for intent, keys in INTENT_QUERY_MAP.items():
            for key in keys:
                assert key in WISDOM_QUERIES, f"{key} missing from WISDOM_QUERIES"

    def test_entity_queries_for_intent(self):
        from app.query.wisdom_collector import _entity_queries_for_intent, ENTITY_QUERIES

        for intent in ["recommendation", "what_if", "dikw_trace"]:
            keys = _entity_queries_for_intent(intent)
            for key in keys:
                assert key in ENTITY_QUERIES, f"{key} missing from ENTITY_QUERIES"


# ── Wisdom Engine tests ─────────────────────────────────────────


class TestWisdomEngine:
    def test_extract_entity_customer(self):
        from app.query.wisdom_engine import _extract_entity

        assert _extract_entity("김민수에게 추천할 상품은?") == "김민수"

    def test_extract_entity_supplier(self):
        from app.query.wisdom_engine import _extract_entity

        assert _extract_entity("애플코리아 공급 중단 시 영향은?") == "애플코리아"

    def test_extract_entity_none(self):
        from app.query.wisdom_engine import _extract_entity

        assert _extract_entity("전체 고객 패턴 분석") is None

    def test_parse_wisdom_response_valid_json(self):
        from app.query.wisdom_engine import _parse_wisdom_response

        valid_json = json.dumps({
            "layers": [
                {"level": "data", "title": "원시 데이터", "content": "테스트", "evidence": ["ev1"]},
                {"level": "information", "title": "구조화", "content": "테스트2", "evidence": []},
                {"level": "knowledge", "title": "지식", "content": "테스트3", "evidence": []},
                {"level": "wisdom", "title": "인사이트", "content": "테스트4", "evidence": ["ev2"]},
            ],
            "summary": "테스트 요약",
            "confidence": "high",
            "action_items": ["행동1", "행동2"],
            "related_queries": ["질문1"],
        })

        layers, summary, confidence, actions, related, tokens = _parse_wisdom_response(valid_json, 100)
        assert len(layers) == 4
        assert layers[0].level == "data"
        assert layers[3].level == "wisdom"
        assert summary == "테스트 요약"
        assert confidence == "high"
        assert len(actions) == 2
        assert tokens == 100

    def test_parse_wisdom_response_markdown_wrapped(self):
        from app.query.wisdom_engine import _parse_wisdom_response

        wrapped = '```json\n{"layers":[],"summary":"wrapped","confidence":"low","action_items":[],"related_queries":[]}\n```'
        layers, summary, confidence, _, _, _ = _parse_wisdom_response(wrapped, 50)
        assert summary == "wrapped"
        assert confidence == "low"
        # Should still have 4 layers (auto-filled)
        assert len(layers) == 4

    def test_parse_wisdom_response_invalid_json_fallback(self):
        from app.query.wisdom_engine import _parse_wisdom_response

        raw_text = "이것은 JSON이 아닙니다. 일반 텍스트 답변입니다."
        layers, summary, confidence, _, _, tokens = _parse_wisdom_response(raw_text, 200)
        assert len(layers) == 4
        assert layers[3].content == raw_text
        assert confidence == "medium"
        assert tokens == 200


# ── Wisdom Response model tests ──────────────────────────────────


class TestWisdomModels:
    def test_dikw_layer_model(self):
        from app.models.schemas import DIKWLayer

        layer = DIKWLayer(level="data", title="원시 데이터", content="테스트")
        assert layer.level == "data"
        assert layer.evidence == []

    def test_wisdom_response_model(self):
        from app.models.schemas import DIKWLayer, WisdomRequest, WisdomResponse

        req = WisdomRequest(question="테스트 질문")
        assert req.question == "테스트 질문"

        resp = WisdomResponse(
            question="테스트",
            intent="pattern",
            dikw_layers=[
                DIKWLayer(level="data", title="D", content="c"),
            ],
            summary="요약",
            confidence="high",
        )
        assert resp.intent == "pattern"
        assert len(resp.dikw_layers) == 1
        assert resp.latency_ms == 0


# ── API endpoint test ────────────────────────────────────────────


class TestWisdomAPI:
    def test_wisdom_endpoint_exists(self):
        """Verify the wisdom router is registered."""
        from app.main import app

        routes = [r.path for r in app.routes]
        assert "/api/v1/wisdom/query" in routes
