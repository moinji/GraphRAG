"""Stage 1: Rule-based query router (regex patterns).

Handles demo questions and common aggregation patterns without LLM.
"""

from __future__ import annotations

import re

# Return type: (template_id, route, slots, params)
RouteResult = tuple[str, str, dict[str, str], dict[str, object]]

# ── Aggregation keyword patterns ────────────────────────────────

AGG_KEYWORDS = re.compile(
    r"(총|합계|평균|COUNT|SUM|AVG|몇\s*개|몇\s*명"
    r"|Top\s*\d+|가장\s*많이|순위|랭킹|상위)",
    re.IGNORECASE,
)

# ── Demo question patterns (Q1, Q2, Q3, Q5) ─────────────────────

# Q1: "X가 주문한 상품"
_Q1_RE = re.compile(
    r"(?:고객\s*)?(?P<name>\S+?)(?:가|이)\s*주문한\s*상품"
)

# Q2: "X가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top N"
_Q2_RE = re.compile(
    r"(?P<name>\S+?)(?:가|이)\s*주문한\s*상품.*카테고리.*리뷰.*(?:평점|평균).*Top\s*(?P<limit>\d+)",
    re.IGNORECASE,
)

# Q3: "가장 많이 팔린 카테고리 Top N" / "Top N 카테고리"
_Q3_RE = re.compile(
    r"(?:가장\s*)?많이\s*팔린\s*카테고리.*Top\s*(?P<limit>\d+)"
    r"|Top\s*(?P<limit2>\d+).*카테고리.*팔린",
    re.IGNORECASE,
)

# Q4: "X와 Y가 공통으로 구매한 상품"
_Q4_RE = re.compile(
    r"(?P<name1>\S+?)(?:와|과)\s*(?P<name2>\S+?)(?:가|이)\s*공통(?:으로)?\s*구매한\s*상품"
)

# Q5: "쿠폰 사용/미사용 비교"
_Q5_RE = re.compile(
    r"쿠폰.*사용.*미사용|미사용.*사용.*비교|쿠폰.*비교",
    re.IGNORECASE,
)


def classify_by_rules(question: str) -> RouteResult | None:
    """Try to match question against rule patterns.

    Returns (template_id, route, slots, params) or None if no match.
    """
    # Q2 must be checked before Q1 (Q2 is a superset pattern)
    m = _Q2_RE.search(question)
    if m:
        name = m.group("name")
        limit = int(m.group("limit"))
        return (
            "custom_q2",
            "cypher_agg",
            {},
            {"name": name, "limit": limit},
        )

    # Q4: common products purchased by two customers
    m = _Q4_RE.search(question)
    if m:
        name1 = m.group("name1")
        name2 = m.group("name2")
        return (
            "custom_q4",
            "cypher_traverse",
            {},
            {"name1": name1, "name2": name2},
        )

    # Q1: two-hop customer→order→product
    m = _Q1_RE.search(question)
    if m:
        name = m.group("name")
        return (
            "two_hop",
            "cypher_traverse",
            {
                "start_label": "Customer",
                "start_prop": "name",
                "rel1": "PLACED",
                "mid_label": "Order",
                "rel2": "CONTAINS",
                "end_label": "Product",
                "return_prop": "name",
            },
            {"val": name},
        )

    # Q3: agg_with_rel for top categories
    m = _Q3_RE.search(question)
    if m:
        limit = int(m.group("limit") or m.group("limit2"))
        return (
            "agg_with_rel",
            "cypher_agg",
            {
                "start_label": "Order",
                "rel1": "CONTAINS",
                "mid_label": "Product",
                "rel2": "BELONGS_TO",
                "end_label": "Category",
                "group_prop": "name",
            },
            {"limit": limit},
        )

    # Q5: coupon comparison
    m = _Q5_RE.search(question)
    if m:
        return (
            "custom_q5",
            "cypher_agg",
            {},
            {},
        )

    return None
