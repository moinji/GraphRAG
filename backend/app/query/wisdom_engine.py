"""Wisdom Engine — orchestrates multi-query collection + LLM insight generation.

DIKW Wisdom layer: Data collection → LLM analysis → structured DIKW response.
"""

from __future__ import annotations

import json
import logging
import re
import time

from app.config import settings
from app.exceptions import WisdomError
from app.models.schemas import DIKWLayer, WisdomResponse
from app.query.wisdom_collector import collect_data
from app.query.wisdom_prompts import (
    WISDOM_SYSTEM_PROMPT,
    build_wisdom_messages,
    serialize_collected_data,
)
from app.query.wisdom_router import WisdomIntent, classify_wisdom_intent

logger = logging.getLogger(__name__)

# Known entities for entity extraction (same as local_search)
_CUSTOMERS = {"김민수", "이영희", "박지훈", "최수진", "정대현"}
_SUPPLIERS = {"애플코리아", "삼성전자", "LG전자"}


def _extract_entity(question: str) -> str | None:
    """Extract entity name from question."""
    for name in _CUSTOMERS:
        if name in question:
            return name
    for name in _SUPPLIERS:
        if name in question:
            return name
    return None


def run_wisdom_query(
    question: str, tenant_id: str | None = None,
) -> WisdomResponse:
    """Full Wisdom pipeline: classify → collect → LLM → parse."""
    start_time = time.time()

    # 1. Classify intent
    intent = classify_wisdom_intent(question)
    if intent == WisdomIntent.LOOKUP:
        # Fallback: treat as pattern analysis
        intent = WisdomIntent.PATTERN

    # 2. Extract entity if present
    entity_name = _extract_entity(question)

    # 3. Collect data from Neo4j (multiple queries)
    collected = collect_data(intent.value, entity_name, tenant_id=tenant_id)
    collected_text = serialize_collected_data(collected)
    queries_used = [k for k, v in collected.items() if v]

    # 4. Call LLM for DIKW analysis
    dikw_layers, summary, confidence, action_items, related_queries, tokens = (
        _generate_wisdom(question, intent.value, collected_text)
    )

    latency_ms = int((time.time() - start_time) * 1000)

    return WisdomResponse(
        question=question,
        intent=intent.value,
        dikw_layers=dikw_layers,
        summary=summary,
        confidence=confidence,
        action_items=action_items,
        related_queries=related_queries,
        cypher_queries_used=queries_used,
        latency_ms=latency_ms,
        llm_tokens_used=tokens,
    )


def _generate_wisdom(
    question: str,
    intent: str,
    collected_text: str,
) -> tuple[list[DIKWLayer], str, str, list[str], list[str], int]:
    """Call LLM and parse structured DIKW response."""
    messages = build_wisdom_messages(question, intent, collected_text)

    # Try OpenAI first
    if settings.openai_api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=settings.wisdom_model,
                max_tokens=settings.wisdom_max_tokens,
                temperature=0,
                messages=[
                    {"role": "system", "content": WISDOM_SYSTEM_PROMPT},
                    *messages,
                ],
            )

            raw_text = response.choices[0].message.content or ""
            tokens = (
                (response.usage.prompt_tokens + response.usage.completion_tokens)
                if response.usage
                else 0
            )

            if response.usage:
                from app.llm_tracker import tracker
                tracker.record(
                    caller="wisdom_engine",
                    model=settings.wisdom_model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                )

            return _parse_wisdom_response(raw_text, tokens)
        except Exception as e:
            logger.warning("OpenAI wisdom failed, trying Anthropic: %s", e)

    # Fallback to Anthropic
    if settings.anthropic_api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.wisdom_max_tokens,
                temperature=0,
                system=WISDOM_SYSTEM_PROMPT,
                messages=messages,
            )

            raw_text = response.content[0].text if response.content else ""
            tokens = response.usage.input_tokens + response.usage.output_tokens

            from app.llm_tracker import tracker
            tracker.record(
                caller="wisdom_engine",
                model=settings.anthropic_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            return _parse_wisdom_response(raw_text, tokens)
        except Exception as e:
            logger.warning("Anthropic wisdom also failed: %s", e)
            raise WisdomError(f"Wisdom LLM generation failed: {e}")

    raise WisdomError("No LLM API key configured for wisdom engine")


def _parse_wisdom_response(
    raw: str, tokens: int
) -> tuple[list[DIKWLayer], str, str, list[str], list[str], int]:
    """Parse LLM JSON response into structured components."""
    # Extract JSON from potential markdown code blocks
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    json_str = json_match.group(1).strip() if json_match else raw.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback: return raw text as wisdom layer
        return (
            [
                DIKWLayer(level="data", title="원시 데이터", content="데이터 수집 완료", evidence=[]),
                DIKWLayer(level="information", title="구조화", content="관계 추출 완료", evidence=[]),
                DIKWLayer(level="knowledge", title="지식", content="그래프 분석 완료", evidence=[]),
                DIKWLayer(level="wisdom", title="인사이트", content=raw, evidence=[]),
            ],
            "분석 결과를 확인하세요.",
            "medium",
            [],
            [],
            tokens,
        )

    layers = []
    for layer_data in data.get("layers", []):
        layers.append(
            DIKWLayer(
                level=layer_data.get("level", ""),
                title=layer_data.get("title", ""),
                content=layer_data.get("content", ""),
                evidence=layer_data.get("evidence", []),
            )
        )

    # Ensure all 4 layers exist
    existing_levels = {l.level for l in layers}
    for level, title in [
        ("data", "원시 데이터"),
        ("information", "구조화된 관계"),
        ("knowledge", "발견된 패턴"),
        ("wisdom", "비즈니스 인사이트"),
    ]:
        if level not in existing_levels:
            layers.append(DIKWLayer(level=level, title=title, content="", evidence=[]))

    # Sort: data → information → knowledge → wisdom
    level_order = {"data": 0, "information": 1, "knowledge": 2, "wisdom": 3}
    layers.sort(key=lambda l: level_order.get(l.level, 99))

    return (
        layers,
        data.get("summary", ""),
        data.get("confidence", "medium"),
        data.get("action_items", []),
        data.get("related_queries", []),
        tokens,
    )
