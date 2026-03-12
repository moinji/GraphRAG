"""Stage 1: Rule-based query router (regex patterns).

Handles demo questions and common aggregation patterns without LLM.
Supports Korean and English questions.
Schema-aware fallbacks for count/property queries on any domain.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Return type: (template_id, route, slots, params)
RouteResult = tuple[str, str, dict[str, str], dict[str, object]]

# ── Synonym normalization ────────────────────────────────────────
# Maps synonyms/alternative expressions to canonical forms used in regex patterns.
# Key = canonical form, Value = list of synonyms (applied case-insensitively).

_SYNONYM_MAP: dict[str, list[str]] = {
    "주문": ["오더", "발주", "결제"],
    "구매": ["구입", "산", "샀"],
    "상품": ["제품", "물건", "아이템", "품목"],
    "고객": ["소비자", "사용자", "유저", "회원", "구매자"],
    "카테고리": ["분류", "범주"],
    "쿠폰": ["할인권", "할인쿠폰"],
    "리뷰": ["후기", "평가", "평점"],
    "공급업체": ["공급자", "납품업체", "벤더"],
    "order": ["purchase"],
    "product": ["item", "merchandise"],
    "customer": ["buyer", "client", "user"],
    "category": ["classification"],
    "coupon": ["discount code", "voucher"],
}


def _normalize_synonyms(text: str) -> str:
    """Replace known synonyms with canonical forms for regex matching."""
    result = text
    for canonical, synonyms in _SYNONYM_MAP.items():
        for syn in synonyms:
            result = re.sub(re.escape(syn), canonical, result, flags=re.IGNORECASE)
    return result

# ── Aggregation keyword patterns ────────────────────────────────

AGG_KEYWORDS = re.compile(
    r"(총|합계|평균|COUNT|SUM|AVG|몇\s*개|몇\s*명"
    r"|Top\s*\d+|가장\s*많이|순위|랭킹|상위"
    r"|total|average|most|how\s*many|ranking)",
    re.IGNORECASE,
)

# ── Demo question patterns (Q1–Q5, Korean + English) ─────────────

# Q1: "X가 주문한 상품" / "What products did X order?"
_Q1_RE = re.compile(
    r"(?:고객\s*)?(?P<name>\S+?)(?:가|이)\s*(?:주문|구매)한\s*상품"
)
_Q1_EN = re.compile(
    r"(?:what\s+)?products?\s+(?:did|has)\s+(?P<name>\S+)\s+order",
    re.IGNORECASE,
)

# Q2: "X가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top N"
_Q2_RE = re.compile(
    r"(?P<name>\S+?)(?:가|이)\s*주문한\s*상품.*카테고리.*리뷰.*(?:평점|평균).*Top\s*(?P<limit>\d+)",
    re.IGNORECASE,
)
_Q2_EN = re.compile(
    r"(?:top|best)\s*(?P<limit>\d+)\s+(?:rated|review).*(?:same|matching)\s+categor.*(?:as\s+)?(?P<name>\S+)",
    re.IGNORECASE,
)

# Q3: "가장 많이 팔린 카테고리 Top N" / "Top N best-selling categories"
_Q3_RE = re.compile(
    r"(?:가장\s*)?많이\s*팔린\s*카테고리.*Top\s*(?P<limit>\d+)"
    r"|Top\s*(?P<limit2>\d+).*카테고리.*팔린",
    re.IGNORECASE,
)
_Q3_EN = re.compile(
    r"top\s*(?P<limit>\d+)\s+(?:best[\s-]*sell|most[\s-]*(?:sold|popular|ordered))\w*\s+categor"
    r"|(?:best[\s-]*sell|most[\s-]*(?:sold|popular|ordered))\w*\s+categor.*top\s*(?P<limit2>\d+)",
    re.IGNORECASE,
)

# Q4: "X와 Y가 공통으로 구매한 상품" / "products both X and Y bought"
_Q4_RE = re.compile(
    r"(?P<name1>\S+?)(?:와|과)\s*(?P<name2>\S+?)(?:가|이)\s*공통(?:으로)?\s*구매한\s*상품"
)
_Q4_EN = re.compile(
    r"(?:products?|items?)\s+(?:both\s+)?(?P<name1>\S+)\s+and\s+(?P<name2>\S+)\s+(?:both\s+)?(?:bought|purchased|ordered)"
    r"|(?:common|shared)\s+(?:products?|items?).*(?P<name1b>\S+)\s+and\s+(?P<name2b>\S+)",
    re.IGNORECASE,
)

# Q5: "쿠폰 사용/미사용 비교" / "coupon used vs unused comparison"
_Q5_RE = re.compile(
    r"쿠폰.*사용.*미사용|미사용.*사용.*비교|쿠폰.*비교",
    re.IGNORECASE,
)
_Q5_EN = re.compile(
    r"coupon.*(?:used|usage).*(?:unused|without|vs)|(?:compare|comparison).*coupon",
    re.IGNORECASE,
)

# ── Extended patterns (Q6–Q12) ───────────────────────────────────

# Q6: 3-hop "X가 주문한 상품의 카테고리/공급업체는?"
_Q6_RE = re.compile(
    r"(?:고객\s*)?(?P<name>\S+?)(?:가|이)\s*(?:주문|구매)한\s*상품(?:의|.*?)\s*(?P<target>카테고리|공급업체)",
)
_Q6_EN = re.compile(
    r"(?:what\s+)?(?P<target>categor\w*|supplier\w*)\s+(?:of|for|in)\s+(?:products?\s+)?(?:ordered|bought|purchased)\s+by\s+(?P<name>\S+)"
    r"|(?P<name2>\S+)(?:'s)?\s+order(?:ed)?\s+(?:products?\s+)?(?P<target2>categor\w*|supplier\w*)",
    re.IGNORECASE,
)

# Q7: reverse 2-hop "X를 주문한 고객은?" / "Who ordered X?"
_Q7_RE = re.compile(
    r"(?P<product>\S+?)(?:를|을)\s*(?:주문|구매|산)한?\s*고객",
)
_Q7_EN = re.compile(
    r"(?:who|which\s+customers?)\s+(?:ordered|bought|purchased)\s+(?P<product>\S+)"
    r"|customers?\s+(?:who|that)\s+(?:ordered|bought|purchased)\s+(?P<product2>\S+)",
    re.IGNORECASE,
)

# Q8: count all "총 X 수는?" / "How many customers/orders/products?"
_ENTITY_LABEL_MAP_KO = {
    "고객": "Customer", "주문": "Order", "상품": "Product",
    "제품": "Product", "카테고리": "Category", "공급업체": "Supplier",
}
_ENTITY_LABEL_MAP_EN = {
    "customer": "Customer", "customers": "Customer",
    "order": "Order", "orders": "Order",
    "product": "Product", "products": "Product",
    "category": "Category", "categories": "Category",
    "supplier": "Supplier", "suppliers": "Supplier",
}
_Q8_RE = re.compile(
    r"총\s*(?P<entity>고객|주문|상품|제품|카테고리|공급업체)\s*(?:건수|수)"
    r"|(?P<entity2>고객|주문|상품|제품|카테고리|공급업체)(?:는|이|가)?\s*(?:총\s*)?몇\s*(?:명|개|건)",
    re.IGNORECASE,
)
_Q8_EN = re.compile(
    r"(?:how\s+many|total(?:\s+number\s+of)?)\s+(?P<entity>customers?|orders?|products?|categories|suppliers?)",
    re.IGNORECASE,
)

# Q9: max/min "가장 비싼 상품은?" / "Most expensive product?"
_Q9_RE = re.compile(
    r"가장\s*(?P<adj>비싼|저렴한|싼|비싸다)\s*(?P<entity>상품|제품)",
)
_Q9_EN = re.compile(
    r"(?:most|least)\s+(?P<adj>expensive|cheap(?:est)?)\s+(?P<entity>products?|items?)",
    re.IGNORECASE,
)

# Q10: 1-hop relationship "X의 카테고리/공급업체/위시리스트/주소는?"
_REL_MAP = {
    "카테고리": ("Product", "BELONGS_TO", "Category", "name", "name"),
    "공급업체": ("Product", "SUPPLIED_BY", "Supplier", "name", "name"),
    "위시리스트": ("Customer", "WISHLISTED", "Product", "name", "name"),
    "주소": ("Customer", "LIVES_AT", "Address", "name", "city"),
    "상위 카테고리": ("Category", "CHILD_OF", "Category", "name", "name"),
}
_Q10_RE = re.compile(
    r"(?P<entity>\S+?)(?:의|[은는])\s*(?P<rel>상위\s*카테고리|카테고리|공급업체|위시리스트(?:\s*(?:에\s*있는\s*)?상품)?|주소)",
)
_Q10_EN = re.compile(
    r"(?:what(?:\s+is)?|show)\s+(?P<entity>\S+?)(?:'s)?\s+(?P<rel>category|supplier|wishlist|address)"
    r"|(?P<rel2>category|supplier|wishlist|address)\s+(?:of|for)\s+(?P<entity2>\S+)",
    re.IGNORECASE,
)
_REL_MAP_EN = {
    "category": "카테고리",
    "supplier": "공급업체",
    "wishlist": "위시리스트",
    "address": "주소",
}

# Q11: property lookup "X의 이메일/전화번호/가격/재고는?"
_PROP_MAP = {
    "이메일": ("Customer", "name", "email"),
    "이메일 주소": ("Customer", "name", "email"),
    "전화번호": ("Customer", "name", "phone"),
    "전화": ("Customer", "name", "phone"),
    "가격": ("Product", "name", "price"),
    "재고": ("Product", "name", "stock"),
    "재고 수량": ("Product", "name", "stock"),
}
_Q11_RE = re.compile(
    r"(?P<entity>\S+?)(?:의|[은는])\s*(?P<prop>이메일\s*주소|이메일|전화번호|전화|가격|재고\s*수량|재고)",
)
_Q11_EN = re.compile(
    r"(?:what(?:\s+is)?)\s+(?P<entity>\S+?)(?:'s)?\s+(?P<prop>email|phone|price|stock|inventory)"
    r"|(?P<prop2>email|phone|price|stock|inventory)\s+(?:of|for)\s+(?P<entity2>\S+)",
    re.IGNORECASE,
)
_PROP_MAP_EN = {
    "email": "이메일",
    "phone": "전화번호",
    "price": "가격",
    "stock": "재고",
    "inventory": "재고",
}

# Q12: group count "고객별 주문 수는?" / "Orders per customer?"
_GROUP_MAP = {
    "고객": ("Customer", "PLACED", "Order", "name"),
    "카테고리": ("Product", "BELONGS_TO", "Category", "name"),
}
_Q12_RE = re.compile(
    r"(?P<group>고객|카테고리)별\s*(?P<target>주문|상품)\s*(?:수|건수|개수)",
)
_Q12_EN = re.compile(
    r"(?P<target>orders?|products?)\s+(?:per|by|for\s+each)\s+(?P<group>customer|category)",
    re.IGNORECASE,
)


# ── Extended patterns (Q13–Q20) ──────────────────────────────────

# Q13: "전체 주문의 평균 금액" → avg_prop
_Q13_RE = re.compile(
    r"(?:전체\s*)?주문(?:의|.*?)\s*평균\s*(?:금액|가격|결제|금)",
    re.IGNORECASE,
)

# Q14: "리뷰 평점 Top N" / "상품별 리뷰 평점 Top N" → review_top_n
_Q14_RE = re.compile(
    r"(?:상품별\s*)?(?:리뷰\s*)?평점\s*Top\s*(?P<limit>\d+)"
    r"|Top\s*(?P<limit2>\d+)\s*(?:리뷰\s*)?평점",
    re.IGNORECASE,
)

# Q15: "배송 상태별" / "결제 방법별" → shipping_stats / payment_stats
_Q15_RE = re.compile(
    r"(?P<prop>배송\s*상태|결제\s*방법|결제\s*수단)별\s*(?:주문\s*)?(?:건수|수|통계|현황|분포)",
    re.IGNORECASE,
)

# Q16: "X 주문의 배송 상태/결제 방법" → order_shipping / order_payment
_Q16_RE = re.compile(
    r"(?P<name>\S+?)\s*주문(?:의|[은는])?\s*(?P<prop>배송\s*상태|결제\s*방법|결제\s*수단)",
    re.IGNORECASE,
)

# Q17: "X 쿠폰을 사용한 주문" → coupon_orders
_Q17_RE = re.compile(
    r"(?P<code>\S+?)\s*쿠폰(?:을|을?\s*)?\s*사용한\s*주문",
    re.IGNORECASE,
)

# Q18: "X에 거주하는 고객" → city_customers
_Q18_RE = re.compile(
    r"(?P<city>\S+?)(?:시|시에|에)\s*거주하는\s*(?:고객|사람|사용자)",
    re.IGNORECASE,
)

# Q19: "X과 Y 카테고리 ... 팔렸" → category_compare
_Q19_RE = re.compile(
    r"(?P<a>\S+?)(?:와|과)\s*(?P<b>\S+?)\s*카테고리.*(?:많이|더|비교)\s*(?:팔|주문|비교)?",
    re.IGNORECASE,
)

# Q20: "X와 Y 공급 상품 비교" → supplier_compare
_Q20_RE = re.compile(
    r"(?P<a>\S+?)(?:와|과)\s*(?P<b>\S+?)\s*(?:공급\s*)?상품\s*비교",
    re.IGNORECASE,
)


def classify_by_rules(question: str, tenant_id: str | None = None) -> RouteResult | None:
    """Try to match question against rule patterns.

    Returns (template_id, route, slots, params) or None if no match.
    Checks both Korean and English patterns.
    Order matters: more specific patterns are checked first.
    Falls back to schema-aware generic patterns for any domain.
    """
    # Normalize synonyms before regex matching
    question = _normalize_synonyms(question)

    # Q2 must be checked before Q1 (Q2 is a superset pattern)
    m = _Q2_RE.search(question)
    if not m:
        m = _Q2_EN.search(question)
    if m:
        name = m.group("name")
        limit = int(m.group("limit"))
        return (
            "custom_q2",
            "cypher_agg",
            {},
            {"name": name, "limit": limit},
        )

    # Q6: 3-hop (must be before Q1, since Q6 contains "주문한 상품")
    m = _Q6_RE.search(question)
    if m:
        name = m.group("name")
        target = m.group("target")
        return _build_three_hop(name, target)
    m = _Q6_EN.search(question)
    if m:
        name = m.group("name") or m.group("name2")
        raw_target = m.group("target") or m.group("target2")
        target = "카테고리" if raw_target.startswith("categor") else "공급업체"
        return _build_three_hop(name, target)

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
    m = _Q4_EN.search(question)
    if m:
        name1 = m.group("name1") or m.group("name1b")
        name2 = m.group("name2") or m.group("name2b")
        return (
            "custom_q4",
            "cypher_traverse",
            {},
            {"name1": name1, "name2": name2},
        )

    # Q7: reverse 2-hop "X를 주문한 고객은?"
    m = _Q7_RE.search(question)
    if m:
        product = m.group("product")
        return (
            "reverse_two_hop",
            "cypher_traverse",
            {
                "end_label": "Customer",
                "rel1": "PLACED",
                "mid_label": "Order",
                "rel2": "CONTAINS",
                "start_label": "Product",
                "start_prop": "name",
                "return_prop": "name",
            },
            {"val": product},
        )
    m = _Q7_EN.search(question)
    if m:
        product = m.group("product") or m.group("product2")
        return (
            "reverse_two_hop",
            "cypher_traverse",
            {
                "end_label": "Customer",
                "rel1": "PLACED",
                "mid_label": "Order",
                "rel2": "CONTAINS",
                "start_label": "Product",
                "start_prop": "name",
                "return_prop": "name",
            },
            {"val": product},
        )

    # Q1: two-hop customer→order→product
    m = _Q1_RE.search(question)
    if not m:
        m = _Q1_EN.search(question)
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
    if not m:
        m = _Q3_EN.search(question)
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
    if not m:
        m = _Q5_EN.search(question)
    if m:
        return (
            "custom_q5",
            "cypher_agg",
            {},
            {},
        )

    # Q10: 1-hop relationship (before Q11 property, since some overlap)
    m = _Q10_RE.search(question)
    if m:
        entity = m.group("entity")
        rel_key = re.sub(r"\s+", " ", m.group("rel")).strip()
        # Normalize: "위시리스트 상품" / "위시리스트에 있는 상품" → "위시리스트"
        if "위시리스트" in rel_key:
            rel_key = "위시리스트"
        if rel_key in _REL_MAP:
            return _build_one_hop(entity, rel_key)
    m = _Q10_EN.search(question)
    if m:
        entity = m.group("entity") or m.group("entity2")
        raw_rel = (m.group("rel") or m.group("rel2")).lower()
        rel_key = _REL_MAP_EN.get(raw_rel)
        if rel_key and rel_key in _REL_MAP:
            return _build_one_hop(entity, rel_key)

    # Q11: direct property lookup
    m = _Q11_RE.search(question)
    if m:
        entity = m.group("entity")
        prop_key = re.sub(r"\s+", " ", m.group("prop")).strip()
        if prop_key in _PROP_MAP:
            label, match_prop, return_prop = _PROP_MAP[prop_key]
            return (
                "property_lookup",
                "cypher_traverse",
                {"label": label, "match_prop": match_prop, "return_prop": return_prop},
                {"val": entity},
            )
    m = _Q11_EN.search(question)
    if m:
        entity = m.group("entity") or m.group("entity2")
        raw_prop = (m.group("prop") or m.group("prop2")).lower()
        prop_key = _PROP_MAP_EN.get(raw_prop)
        if prop_key and prop_key in _PROP_MAP:
            label, match_prop, return_prop = _PROP_MAP[prop_key]
            return (
                "property_lookup",
                "cypher_traverse",
                {"label": label, "match_prop": match_prop, "return_prop": return_prop},
                {"val": entity},
            )

    # Q9: max/min property
    m = _Q9_RE.search(question)
    if m:
        return (
            "max_prop",
            "cypher_agg",
            {"label": "Product", "return_prop": "name", "sort_prop": "price"},
            {},
        )
    m = _Q9_EN.search(question)
    if m:
        return (
            "max_prop",
            "cypher_agg",
            {"label": "Product", "return_prop": "name", "sort_prop": "price"},
            {},
        )

    # Q8: count all
    m = _Q8_RE.search(question)
    if m:
        raw_entity = m.group("entity") or m.group("entity2")
        label = _ENTITY_LABEL_MAP_KO.get(raw_entity)
        if label:
            return (
                "count_all",
                "cypher_agg",
                {"label": label},
                {},
            )
    m = _Q8_EN.search(question)
    if m:
        raw_entity = m.group("entity").lower()
        label = _ENTITY_LABEL_MAP_EN.get(raw_entity)
        if label:
            return (
                "count_all",
                "cypher_agg",
                {"label": label},
                {},
            )

    # Q12: group count
    m = _Q12_RE.search(question)
    if m:
        group_key = m.group("group")
        return _build_group_count_ko(group_key, m.group("target"))
    m = _Q12_EN.search(question)
    if m:
        group_key = m.group("group").lower()
        target = m.group("target").lower()
        return _build_group_count_en(group_key, target)

    # Q16: customer order property (before Q13/Q15 to avoid partial match)
    m = _Q16_RE.search(question)
    if m:
        name = m.group("name")
        prop = re.sub(r"\s+", " ", m.group("prop")).strip()
        if "배송" in prop:
            return ("order_shipping", "cypher_traverse", {}, {"name": name})
        return ("order_payment", "cypher_traverse", {}, {"name": name})

    # Q14: review/rating Top N (before Q13 avg to avoid overlap)
    m = _Q14_RE.search(question)
    if m:
        limit = int(m.group("limit") or m.group("limit2"))
        return ("review_top_n", "cypher_agg", {}, {"limit": limit})

    # Q13: average aggregate
    m = _Q13_RE.search(question)
    if m:
        return (
            "avg_prop",
            "cypher_agg",
            {"label": "Order", "prop": "total_amount"},
            {},
        )

    # Q15: property group by (shipping/payment stats)
    m = _Q15_RE.search(question)
    if m:
        prop = re.sub(r"\s+", " ", m.group("prop")).strip()
        if "배송" in prop:
            return ("shipping_stats", "cypher_agg", {}, {})
        return ("payment_stats", "cypher_agg", {}, {})

    # Q17: coupon filter
    m = _Q17_RE.search(question)
    if m:
        code = m.group("code")
        return ("coupon_orders", "cypher_traverse", {}, {"code": code})

    # Q18: city filter
    m = _Q18_RE.search(question)
    if m:
        city = m.group("city")
        return ("city_customers", "cypher_traverse", {}, {"city": city})

    # Q20: supplier comparison (before Q19 category to avoid overlap)
    m = _Q20_RE.search(question)
    if m:
        a, b = m.group("a"), m.group("b")
        return ("supplier_compare", "cypher_agg", {}, {"val1": a, "val2": b})

    # Q19: category comparison
    m = _Q19_RE.search(question)
    if m:
        a, b = m.group("a"), m.group("b")
        return ("category_compare", "cypher_agg", {}, {"val1": a, "val2": b})

    # ── Schema-aware generic fallbacks ──────────────────────────────
    schema_result = _try_schema_aware_match(question, tenant_id)
    if schema_result is not None:
        return schema_result

    return None


# ── Helper builders ──────────────────────────────────────────────

def _build_three_hop(name: str, target: str) -> RouteResult:
    """Build three_hop route for category or supplier."""
    if target == "카테고리":
        return (
            "three_hop",
            "cypher_traverse",
            {
                "start_label": "Customer",
                "start_prop": "name",
                "rel1": "PLACED",
                "mid1_label": "Order",
                "rel2": "CONTAINS",
                "mid2_label": "Product",
                "rel3": "BELONGS_TO",
                "end_label": "Category",
                "return_prop": "name",
            },
            {"val": name},
        )
    # 공급업체
    return (
        "three_hop",
        "cypher_traverse",
        {
            "start_label": "Customer",
            "start_prop": "name",
            "rel1": "PLACED",
            "mid1_label": "Order",
            "rel2": "CONTAINS",
            "mid2_label": "Product",
            "rel3": "SUPPLIED_BY",
            "end_label": "Supplier",
            "return_prop": "name",
        },
        {"val": name},
    )


def _build_one_hop(entity: str, rel_key: str) -> RouteResult:
    """Build one_hop_out route from relationship map."""
    start_label, rel_type, end_label, start_prop, return_prop = _REL_MAP[rel_key]
    return (
        "one_hop_out",
        "cypher_traverse",
        {
            "start_label": start_label,
            "start_prop": start_prop,
            "rel1": rel_type,
            "end_label": end_label,
            "return_prop": return_prop,
        },
        {"val": entity},
    )


def _build_group_count_ko(group_key: str, target: str) -> RouteResult:
    """Build group_count route from Korean group key."""
    if group_key == "고객":
        return (
            "group_count",
            "cypher_agg",
            {"start_label": "Customer", "rel1": "PLACED", "end_label": "Order", "group_prop": "name"},
            {},
        )
    # 카테고리별 상품 수
    return (
        "top_n",
        "cypher_agg",
        {"start_label": "Product", "rel1": "BELONGS_TO", "end_label": "Category", "group_prop": "name"},
        {"limit": 100},
    )


def _build_group_count_en(group_key: str, target: str) -> RouteResult:
    """Build group_count route from English group key."""
    if group_key == "customer":
        return (
            "group_count",
            "cypher_agg",
            {"start_label": "Customer", "rel1": "PLACED", "end_label": "Order", "group_prop": "name"},
            {},
        )
    # category
    return (
        "top_n",
        "cypher_agg",
        {"start_label": "Product", "rel1": "BELONGS_TO", "end_label": "Category", "group_prop": "name"},
        {"limit": 100},
    )


# ── Schema-aware generic patterns ────────────────────────────────

# Generic count pattern: "총 X 수는?" / "How many X?"
_GENERIC_COUNT_KO = re.compile(
    r"총\s*(?P<entity>\S+?)\s*수"
    r"|(?P<entity2>\S+?)(?:는|이|가)?\s*(?:총\s*)?몇\s*(?:명|개|건)"
)
_GENERIC_COUNT_EN = re.compile(
    r"(?:how\s+many|total(?:\s+number\s+of)?)\s+(?P<entity>\w+)",
    re.IGNORECASE,
)

# Generic property lookup: "X의 Y는?" / "What is X's Y?"
_GENERIC_PROP_KO = re.compile(
    r"(?P<entity>\S+?)(?:의|[은는])\s*(?P<prop>\S+?)(?:은|는|이|가|을|를)?"
    r"\s*(?:무엇|뭐|얼마|어떻게|몇)",
)
_GENERIC_PROP_EN = re.compile(
    r"(?:what(?:\s+is)?)\s+(?P<entity>\S+?)(?:'s)?\s+(?P<prop>\w+)"
    r"|(?P<prop2>\w+)\s+(?:of|for)\s+(?P<entity2>\S+)",
    re.IGNORECASE,
)


def _get_schema_labels(tenant_id: str | None = None) -> list[str]:
    """Get node labels from graph schema (cached). Returns [] on failure."""
    try:
        from app.db.graph_schema import get_graph_schema
        schema = get_graph_schema(tenant_id)
        return schema.get("node_labels", [])
    except Exception:
        return []


def _get_schema_properties(tenant_id: str | None = None) -> dict[str, list[str]]:
    """Get node properties from graph schema (cached). Returns {} on failure."""
    try:
        from app.db.graph_schema import get_graph_schema
        schema = get_graph_schema(tenant_id)
        return schema.get("node_properties", {})
    except Exception:
        return {}


def _depluralize(word: str) -> str:
    """Naive English depluralization."""
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"  # policies → policy
    if w.endswith("es") and len(w) > 3:
        return w[:-2]  # classes → class
    if w.endswith("s") and len(w) > 2:
        return w[:-1]  # students → student
    return w


def _fuzzy_match_label(text: str, labels: list[str]) -> str | None:
    """Match a text fragment to a Neo4j label (case-insensitive, singular/plural)."""
    lower = text.lower()
    singular = _depluralize(lower)
    for label in labels:
        ll = label.lower()
        if ll == lower or ll == singular or _depluralize(ll) == singular:
            return label
    return None


def _try_schema_aware_match(question: str, tenant_id: str | None) -> RouteResult | None:
    """Try schema-aware generic patterns against live Neo4j labels."""
    # Generic count: "총 학생 수는?" / "How many policies?"
    m = _GENERIC_COUNT_KO.search(question)
    if m:
        entity_text = m.group("entity") or m.group("entity2")
        if entity_text:
            labels = _get_schema_labels(tenant_id)
            label = _fuzzy_match_label(entity_text, labels)
            if label:
                return ("count_all", "cypher_agg", {"label": label}, {})

    m = _GENERIC_COUNT_EN.search(question)
    if m:
        entity_text = m.group("entity")
        if entity_text:
            labels = _get_schema_labels(tenant_id)
            label = _fuzzy_match_label(entity_text, labels)
            if label:
                return ("count_all", "cypher_agg", {"label": label}, {})

    # Generic property lookup: "홍길동의 email은?" / "What is 홍길동's phone?"
    m = _GENERIC_PROP_EN.search(question)
    if m:
        entity_text = m.group("entity") or m.group("entity2")
        prop_text = m.group("prop") or m.group("prop2")
        if entity_text and prop_text:
            props = _get_schema_properties(tenant_id)
            for label, prop_list in props.items():
                prop_lower = prop_text.lower()
                if prop_lower in [p.lower() for p in prop_list]:
                    actual_prop = next(p for p in prop_list if p.lower() == prop_lower)
                    return (
                        "property_lookup",
                        "cypher_traverse",
                        {"label": label, "match_prop": "name", "return_prop": actual_prop},
                        {"val": entity_text},
                    )

    return None
