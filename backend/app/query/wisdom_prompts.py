"""Wisdom Engine system prompts and data serialization."""

from __future__ import annotations

WISDOM_SYSTEM_PROMPT = """\
당신은 Knowledge Graph 기반 비즈니스 인텔리전스 어드바이저입니다.
고객의 데이터에서 추출한 그래프 구조와 집계 결과를 분석하여 actionable insight를 제공합니다.

## 분석 원칙

1. **DIKW 프레임워크 준수**: 모든 답변에서 4계층을 명시적으로 구분합니다.
2. **근거 기반**: 모든 인사이트는 그래프 데이터에 근거해야 합니다. 추측은 "[추정]"으로 표시합니다.
3. **정량화**: 가능한 경우 수치를 포함합니다 (비율, 건수, 금액 등).
4. **행동 제안**: 단순 관찰이 아닌, 구체적으로 "무엇을 해야 하는지"를 제안합니다.
5. **한국어 답변**: 모든 답변은 한국어로 작성합니다.

## 반드시 아래 JSON 형식으로만 답변하세요

```json
{
  "layers": [
    {
      "level": "data",
      "title": "원시 데이터",
      "content": "분석에 사용된 데이터 출처와 규모 설명",
      "evidence": ["테이블명 또는 데이터 포인트"]
    },
    {
      "level": "information",
      "title": "구조화된 관계",
      "content": "ERD/FK에서 추출한 관계 구조 설명",
      "evidence": ["관계 설명"]
    },
    {
      "level": "knowledge",
      "title": "발견된 패턴",
      "content": "그래프 탐색으로 발견한 패턴과 연결 설명",
      "evidence": ["패턴/연결 근거"]
    },
    {
      "level": "wisdom",
      "title": "비즈니스 인사이트",
      "content": "의사결정에 활용 가능한 인사이트와 행동 제안",
      "evidence": ["인사이트 근거"]
    }
  ],
  "summary": "핵심 한 줄 요약",
  "confidence": "high 또는 medium 또는 low",
  "action_items": ["구체적 행동 제안 1", "구체적 행동 제안 2"],
  "related_queries": ["추가로 탐색해볼 질문 1", "추가로 탐색해볼 질문 2"]
}
```

위 JSON 외의 텍스트는 절대 포함하지 마세요. JSON만 출력하세요.
"""


def serialize_collected_data(data: dict[str, list[dict]]) -> str:
    """Convert collected multi-query results into structured text for LLM context."""
    sections: list[str] = []

    for query_key, records in data.items():
        if not records:
            continue

        label = _QUERY_LABELS.get(query_key, query_key)
        sections.append(f"=== {label} ===")

        for i, rec in enumerate(records, 1):
            parts = []
            for k, v in rec.items():
                if v is not None:
                    parts.append(f"{k}={v}")
            sections.append(f"  {i}. {', '.join(parts)}")

        sections.append("")

    return "\n".join(sections)


_QUERY_LABELS: dict[str, str] = {
    "customer_segments": "고객 세그먼트 (주문금액 기준)",
    "category_distribution": "카테고리별 주문 분포",
    "co_purchase": "동시구매 패턴",
    "supplier_dependency": "공급사 의존도",
    "review_quality": "상품별 리뷰 평점 vs 판매량",
    "coupon_impact": "쿠폰 사용 영향",
    "payment_methods": "결제 수단 통계",
    "customer_orders": "대상 고객 주문 내역",
    "customer_reviews": "대상 고객 리뷰 내역",
    "customer_graph_2hop": "대상 고객 그래프 (2홉)",
    "supplier_impact": "공급사 제거 영향",
    "supplier_alternatives": "대체 공급사/상품",
    "recommendation_collab": "협업 필터링 추천",
}


def build_wisdom_messages(
    question: str,
    intent: str,
    collected_text: str,
) -> list[dict[str, str]]:
    """Build message list for LLM call."""
    intent_context = _INTENT_INSTRUCTIONS.get(intent, "")

    return [
        {
            "role": "user",
            "content": (
                f"분석 의도: {intent}\n"
                f"{intent_context}\n\n"
                f"수집된 그래프 데이터:\n{collected_text}\n\n"
                f"질문: {question}"
            ),
        },
    ]


_INTENT_INSTRUCTIONS: dict[str, str] = {
    "pattern": "고객/상품/카테고리 데이터에서 비즈니스 패턴과 트렌드를 발견하세요.",
    "causal": "변수 간 상관관계를 분석하고, 가능한 인과관계를 추론하세요. 상관관계와 인과관계를 구분하세요.",
    "recommendation": "그래프 데이터 기반으로 구체적 추천과 근거를 제시하세요. 협업 필터링 결과가 있으면 활용하세요.",
    "what_if": "제거/변경 시 영향 범위를 정량화하고 리스크 완화 방안을 제시하세요.",
    "dikw_trace": "DIKW 피라미드의 각 계층을 명확히 구분하여 종합 보고서를 작성하세요.",
}
