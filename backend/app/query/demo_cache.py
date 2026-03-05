"""Golden answer cache for 5 demo questions.

Pre-computed answers based on seed data for deterministic demo replay.
Used in mode="a" pipeline to bypass Neo4j when cache hits.
"""

from __future__ import annotations

from app.models.schemas import QueryResponse
from app.query.template_registry import get_cypher, render_cypher

# ── Cached demo answers (seed data ground truth) ─────────────────

_CACHE: dict[str, QueryResponse] = {
    "고객 김민수가 주문한 상품은?": QueryResponse(
        question="고객 김민수가 주문한 상품은?",
        answer="김민수 고객이 주문한 상품: 맥북프로, 에어팟프로, 갤럭시탭",
        cypher=render_cypher("two_hop", {
            "start_label": "Customer", "start_prop": "name",
            "rel1": "PLACED", "mid_label": "Order",
            "rel2": "CONTAINS", "end_label": "Product",
            "return_prop": "name",
        }),
        paths=[
            "Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(맥북프로)",
            "Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(에어팟프로)",
            "Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(갤럭시탭)",
        ],
        template_id="two_hop",
        route="cypher_traverse",
        matched_by="rule",
        mode="a",
        cached=True,
        latency_ms=0,
        related_node_ids=["Customer_1", "Product_1", "Product_2", "Product_3"],
    ),
    "김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?": QueryResponse(
        question="김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?",
        answer=(
            "김민수가 주문한 상품 카테고리 내 리뷰 평점 Top 3: "
            "1위 맥북에어(노트북, 평점 5.0), "
            "2위 에어팟프로(오디오, 평점 4.67), "
            "3위 아이패드에어(태블릿, 평점 4.5)"
        ),
        cypher=get_cypher("custom_q2"),
        paths=[
            "Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(*) "
            "-> BELONGS_TO -> Category(노트북) "
            "<- BELONGS_TO <- Product(맥북에어) "
            "<- REVIEWS <- Review [avg=5.0]",
            "Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(*) "
            "-> BELONGS_TO -> Category(오디오) "
            "<- BELONGS_TO <- Product(에어팟프로) "
            "<- REVIEWS <- Review [avg=4.67]",
            "Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(*) "
            "-> BELONGS_TO -> Category(태블릿) "
            "<- BELONGS_TO <- Product(아이패드에어) "
            "<- REVIEWS <- Review [avg=4.5]",
        ],
        template_id="custom_q2",
        route="cypher_agg",
        matched_by="rule",
        mode="a",
        cached=True,
        latency_ms=0,
        related_node_ids=["Customer_1", "Product_7", "Product_2", "Product_6", "Category_4", "Category_5", "Category_6"],
    ),
    "가장 많이 팔린 카테고리 Top 3는?": QueryResponse(
        question="가장 많이 팔린 카테고리 Top 3는?",
        answer="가장 많이 팔린 카테고리 Top 3: 1위 노트북(6건), 2위 오디오(4건), 3위 태블릿(2건)",
        cypher=render_cypher("agg_with_rel", {
            "start_label": "Order", "rel1": "CONTAINS",
            "mid_label": "Product", "rel2": "BELONGS_TO",
            "end_label": "Category", "group_prop": "name",
        }),
        paths=[
            "Order(*) -> CONTAINS -> Product(*) -> BELONGS_TO -> Category(노트북) [count=6]",
            "Order(*) -> CONTAINS -> Product(*) -> BELONGS_TO -> Category(오디오) [count=4]",
            "Order(*) -> CONTAINS -> Product(*) -> BELONGS_TO -> Category(태블릿) [count=2]",
        ],
        template_id="agg_with_rel",
        route="cypher_agg",
        matched_by="rule",
        mode="a",
        cached=True,
        latency_ms=0,
        related_node_ids=["Category_4", "Category_5", "Category_6"],
    ),
    "김민수와 이영희가 공통으로 구매한 상품은?": QueryResponse(
        question="김민수와 이영희가 공통으로 구매한 상품은?",
        answer="공통 구매 상품: 맥북프로",
        cypher=get_cypher("custom_q4"),
        paths=["Product(맥북프로)"],
        template_id="custom_q4",
        route="cypher_traverse",
        matched_by="rule",
        mode="a",
        cached=True,
        latency_ms=0,
        related_node_ids=["Customer_1", "Customer_2", "Product_1"],
    ),
    "쿠폰 사용 주문과 미사용 주문의 평균 금액 비교": QueryResponse(
        question="쿠폰 사용 주문과 미사용 주문의 평균 금액 비교",
        answer="쿠폰 사용: 3건, 평균 1793367원 | 쿠폰 미사용: 5건, 평균 2622800원",
        cypher=get_cypher("custom_q5"),
        paths=[
            "Order(*) -> APPLIED -> Coupon [status=used, count=3, avg=1793367]",
            "Order(*) -> APPLIED -> Coupon [status=unused, count=5, avg=2622800]",
        ],
        template_id="custom_q5",
        route="cypher_agg",
        matched_by="rule",
        mode="a",
        cached=True,
        latency_ms=0,
        related_node_ids=[],
    ),
}


def get_cached_answer(question: str) -> QueryResponse | None:
    """Look up a pre-computed answer for a demo question.

    Returns a QueryResponse with cached=True if found, None otherwise.
    """
    return _CACHE.get(question)
