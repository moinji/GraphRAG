"""Golden answer cache for 5 demo questions.

Pre-computed answers based on seed data for deterministic demo replay.
Used in mode="a" pipeline to bypass Neo4j when cache hits.
"""

from __future__ import annotations

from app.models.schemas import QueryResponse

# ── Cached demo answers (seed data ground truth) ─────────────────

_CACHE: dict[str, QueryResponse] = {
    "고객 김민수가 주문한 상품은?": QueryResponse(
        question="고객 김민수가 주문한 상품은?",
        answer="김민수 고객이 주문한 상품: 맥북프로, 에어팟프로, 갤럭시탭",
        cypher=(
            "MATCH (a:Customer {name: $val})"
            "-[:PLACED]->(b:Order)"
            "-[:CONTAINS]->(c:Product) "
            "RETURN DISTINCT c.name AS result"
        ),
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
    ),
    "김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?": QueryResponse(
        question="김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?",
        answer=(
            "김민수가 주문한 상품 카테고리 내 리뷰 평점 Top 3: "
            "1위 맥북에어(노트북, 평점 5.0), "
            "2위 에어팟프로(오디오, 평점 4.67), "
            "3위 아이패드에어(태블릿, 평점 4.5)"
        ),
        cypher=(
            "MATCH (c:Customer {name: $name})"
            "-[:PLACED]->(:Order)"
            "-[:CONTAINS]->(p:Product)"
            "-[:BELONGS_TO]->(cat:Category) "
            "WITH collect(DISTINCT cat) AS cats "
            "UNWIND cats AS cat "
            "MATCH (p2:Product)-[:BELONGS_TO]->(cat) "
            "MATCH (rev:Review)-[:REVIEWS]->(p2) "
            "WITH p2.name AS product, cat.name AS category, "
            "round(avg(toFloat(rev.rating)) * 100) / 100 AS avg_rating "
            "ORDER BY avg_rating DESC LIMIT $limit "
            "RETURN product, category, avg_rating"
        ),
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
    ),
    "가장 많이 팔린 카테고리 Top 3는?": QueryResponse(
        question="가장 많이 팔린 카테고리 Top 3는?",
        answer="가장 많이 팔린 카테고리 Top 3: 1위 노트북(6건), 2위 오디오(4건), 3위 태블릿(2건)",
        cypher=(
            "MATCH (a:Order)-[:CONTAINS]->(b:Product)-[:BELONGS_TO]->(c:Category) "
            "RETURN c.name AS category, count(DISTINCT a) AS order_count "
            "ORDER BY order_count DESC LIMIT $limit"
        ),
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
    ),
    "김민수와 이영희가 공통으로 구매한 상품은?": QueryResponse(
        question="김민수와 이영희가 공통으로 구매한 상품은?",
        answer="공통 구매 상품: 맥북프로",
        cypher=(
            "MATCH (c1:Customer {name: $name1})-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product) "
            "WHERE EXISTS { "
            "MATCH (c2:Customer {name: $name2})-[:PLACED]->(:Order)-[:CONTAINS]->(p) "
            "} "
            "RETURN DISTINCT p.name AS product"
        ),
        paths=["Product(맥북프로)"],
        template_id="custom_q4",
        route="cypher_traverse",
        matched_by="rule",
        mode="a",
        cached=True,
        latency_ms=0,
    ),
    "쿠폰 사용 주문과 미사용 주문의 평균 금액 비교": QueryResponse(
        question="쿠폰 사용 주문과 미사용 주문의 평균 금액 비교",
        answer="쿠폰 사용: 3건, 평균 1793367원 | 쿠폰 미사용: 5건, 평균 2622800원",
        cypher=(
            "MATCH (o:Order) "
            "OPTIONAL MATCH (o)-[:APPLIED]->(coup:Coupon) "
            "WITH CASE WHEN coup IS NOT NULL THEN 'used' ELSE 'unused' END AS coupon_status, "
            "toFloat(o.total_amount) AS amt "
            "RETURN coupon_status, count(*) AS order_count, "
            "round(avg(amt) * 100) / 100 AS avg_amount"
        ),
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
    ),
}


def get_cached_answer(question: str) -> QueryResponse | None:
    """Look up a pre-computed answer for a demo question.

    Returns a QueryResponse with cached=True if found, None otherwise.
    """
    return _CACHE.get(question)
