"""Golden answer cache for Mode C demo questions.

Pre-computed answers for deterministic demo replay of hybrid search.
Used in mode="c" pipeline to bypass vector search + LLM when cache hits.
"""

from __future__ import annotations

from app.models.schemas import DocumentSource, QueryResponse

_CACHE_C: dict[str, QueryResponse] = {
    "맥북프로의 배터리 수명은 얼마나 되나요?": QueryResponse(
        question="맥북프로의 배터리 수명은 얼마나 되나요?",
        answer=(
            "맥북프로의 배터리 수명은 14인치 기준 최대 22시간, 16인치 기준 최대 24시간의 "
            "비디오 재생이 가능합니다. MagSafe 3 또는 USB-C 고속 충전을 지원하며, "
            "30분 충전으로 약 50%까지 충전됩니다."
        ),
        cypher="",
        paths=["[문서: 맥북프로_제품설명.md]"],
        template_id="hybrid_search",
        route="hybrid",
        matched_by="hybrid_c",
        mode="c",
        cached=True,
        latency_ms=0,
        document_sources=[
            DocumentSource(
                document_id=1,
                filename="맥북프로_제품설명.md",
                chunk_text=(
                    "맥북프로의 배터리 수명은 최대 22시간(14인치 기준)으로 역대 Mac 중 "
                    "가장 긴 배터리 수명을 제공합니다. 16인치 모델은 최대 24시간의 "
                    "비디오 재생이 가능합니다."
                ),
                relevance_score=0.92,
                page_num=1,
                chunk_index=2,
            ),
        ],
    ),
    "에어팟프로의 노이즈캔슬링 기능에 대해 설명해주세요.": QueryResponse(
        question="에어팟프로의 노이즈캔슬링 기능에 대해 설명해주세요.",
        answer=(
            "에어팟프로는 H2 칩 기반의 액티브 노이즈캔슬링(ANC)을 탑재하여 "
            "외부 소음을 최대 2배 더 효과적으로 차단합니다. "
            "또한 적응형 오디오 기능으로 주변 환경에 따라 노이즈캔슬링 수준을 "
            "자동 조절하며, 대화 인식 기능으로 주변 사람과 대화 시 "
            "자동으로 볼륨을 낮추고 외부 소리를 증폭합니다."
        ),
        cypher="",
        paths=["[문서: 에어팟프로_제품설명.md]"],
        template_id="hybrid_search",
        route="hybrid",
        matched_by="hybrid_c",
        mode="c",
        cached=True,
        latency_ms=0,
        document_sources=[
            DocumentSource(
                document_id=2,
                filename="에어팟프로_제품설명.md",
                chunk_text=(
                    "액티브 노이즈캔슬링 (ANC): H2 칩 기반으로 외부 소음을 최대 2배 더 "
                    "효과적으로 차단합니다. 적응형 오디오: 주변 환경에 따라 "
                    "노이즈캔슬링 수준을 자동으로 조절합니다."
                ),
                relevance_score=0.95,
                page_num=1,
                chunk_index=1,
            ),
        ],
    ),
    "김민수가 주문한 맥북프로의 주요 사양은?": QueryResponse(
        question="김민수가 주문한 맥북프로의 주요 사양은?",
        answer=(
            "김민수 고객이 주문한 맥북프로의 주요 사양입니다:\n\n"
            "[그래프] 김민수 → PLACED → Order → CONTAINS → 맥북프로\n\n"
            "[문서] 맥북프로 사양:\n"
            "- 프로세서: Apple M3 Pro / M3 Max\n"
            "- 메모리: 18GB~48GB 통합 메모리\n"
            "- 디스플레이: 14.2인치/16.2인치 Liquid Retina XDR\n"
            "- 배터리: 최대 22시간(14인치)\n"
            "- 무게: 14인치 1.55kg"
        ),
        cypher="",
        paths=[
            "[그래프] Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(맥북프로)",
            "[문서: 맥북프로_제품설명.md]",
        ],
        template_id="hybrid_search",
        route="hybrid",
        matched_by="hybrid_c",
        mode="c",
        cached=True,
        latency_ms=0,
        subgraph_context=(
            "[그래프 컨텍스트]\n"
            "Customer(김민수):\n"
            "  -PLACED-> Order(ORD-001)\n"
            "  -PLACED-> Order(ORD-002)"
        ),
        document_sources=[
            DocumentSource(
                document_id=1,
                filename="맥북프로_제품설명.md",
                chunk_text=(
                    "프로세서: Apple M3 Pro / M3 Max, 메모리: 18GB / 36GB / 48GB 통합 메모리, "
                    "저장장치: 512GB~4TB SSD, 디스플레이: 14.2인치 또는 16.2인치 Liquid Retina XDR"
                ),
                relevance_score=0.88,
                page_num=1,
                chunk_index=1,
            ),
        ],
        related_node_ids=["Customer_1", "Product_1"],
    ),
    "반품 정책은 어떻게 되나요?": QueryResponse(
        question="반품 정책은 어떻게 되나요?",
        answer=(
            "반품/교환 정책:\n"
            "- 상품 수령 후 7일 이내 신청 가능\n"
            "- 단순 변심 반품 시 왕복 배송비 6,000원 고객 부담\n"
            "- 상품 불량/오배송 시 무료 반품/교환\n"
            "- 사용 흔적이 있는 상품은 반품 불가"
        ),
        cypher="",
        paths=["[문서: 쇼핑몰_이용안내.md]"],
        template_id="hybrid_search",
        route="hybrid",
        matched_by="hybrid_c",
        mode="c",
        cached=True,
        latency_ms=0,
        document_sources=[
            DocumentSource(
                document_id=3,
                filename="쇼핑몰_이용안내.md",
                chunk_text=(
                    "상품 수령 후 7일 이내 반품/교환 신청 가능. "
                    "단순 변심에 의한 반품 시 왕복 배송비 6,000원 고객 부담. "
                    "상품 불량 또는 오배송 시 무료 반품/교환."
                ),
                relevance_score=0.91,
                page_num=1,
                chunk_index=3,
            ),
        ],
    ),
    "애플코리아가 공급하는 제품들의 특징은?": QueryResponse(
        question="애플코리아가 공급하는 제품들의 특징은?",
        answer=(
            "애플코리아가 공급하는 제품 정보입니다:\n\n"
            "[그래프] 애플코리아 → SUPPLIES → 맥북프로, 에어팟프로, 아이패드에어, 맥북에어\n\n"
            "[문서] 주요 특징:\n"
            "- 맥북프로: M3 Pro/Max 칩, 최대 22시간 배터리, Liquid Retina XDR 디스플레이\n"
            "- 에어팟프로: H2 칩 ANC, 적응형 오디오, 최대 30시간 배터리(케이스 포함)"
        ),
        cypher="",
        paths=[
            "[그래프] Supplier(애플코리아) -> SUPPLIES -> Product(맥북프로)",
            "[그래프] Supplier(애플코리아) -> SUPPLIES -> Product(에어팟프로)",
            "[문서: 맥북프로_제품설명.md]",
            "[문서: 에어팟프로_제품설명.md]",
        ],
        template_id="hybrid_search",
        route="hybrid",
        matched_by="hybrid_c",
        mode="c",
        cached=True,
        latency_ms=0,
        subgraph_context=(
            "[그래프 컨텍스트]\n"
            "Supplier(애플코리아):\n"
            "  -SUPPLIES-> Product(맥북프로)\n"
            "  -SUPPLIES-> Product(에어팟프로)\n"
            "  -SUPPLIES-> Product(아이패드에어)\n"
            "  -SUPPLIES-> Product(맥북에어)"
        ),
        document_sources=[
            DocumentSource(
                document_id=1,
                filename="맥북프로_제품설명.md",
                chunk_text="맥북프로는 Apple이 설계한 프로페셔널 노트북입니다. M3 Pro 또는 M3 Max 칩 탑재.",
                relevance_score=0.85,
                page_num=1,
                chunk_index=0,
            ),
            DocumentSource(
                document_id=2,
                filename="에어팟프로_제품설명.md",
                chunk_text="에어팟프로는 Apple의 프리미엄 무선 이어폰으로, 액티브 노이즈캔슬링(ANC) 제공.",
                relevance_score=0.83,
                page_num=1,
                chunk_index=0,
            ),
        ],
        related_node_ids=["Supplier_1", "Product_1", "Product_2", "Product_6", "Product_7"],
    ),
}


def get_cached_answer_c(question: str) -> QueryResponse | None:
    """Look up a pre-computed Mode C answer for a demo question."""
    return _CACHE_C.get(question)
