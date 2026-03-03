"""B안 Local Search: entity extraction → subgraph → LLM answer.

Self-implemented GraphRAG local search (no Microsoft dependency).
"""

from __future__ import annotations

import logging
import re
import time

from neo4j import GraphDatabase

from app.config import settings
from app.exceptions import LocalSearchError
from app.models.schemas import QueryResponse
from app.query.local_prompts import (
    LOCAL_SEARCH_SYSTEM_PROMPT,
    build_local_search_messages,
    parse_local_answer,
    serialize_aggregate_results,
    serialize_subgraph,
)

logger = logging.getLogger(__name__)

# ── Known entities from seed data (rule-based extraction) ────────

_CUSTOMERS = {"김민수", "이영희", "박지훈", "최수진", "정대현"}
_PRODUCTS = {
    "맥북프로", "에어팟프로", "갤럭시탭", "LG그램", "갤럭시버즈",
    "아이패드에어", "맥북에어", "소니WH-1000XM5",
}
_CATEGORIES = {"전자기기", "의류", "식품", "노트북", "오디오", "태블릿"}
_SUPPLIERS = {"애플코리아", "삼성전자", "LG전자"}

# Aggregate question patterns (no specific entity anchor)
_AGGREGATE_PATTERNS = [
    re.compile(r"(가장|많이|top|순위|평균|총|합계|통계|전체)", re.IGNORECASE),
    re.compile(r"(카테고리별|고객별|상품별|월별|주문별)", re.IGNORECASE),
    re.compile(r"(몇\s*개|몇\s*명|몇\s*건)", re.IGNORECASE),
]


def extract_entity(question: str) -> tuple[str | None, str | None]:
    """Extract the main entity from a question using rules.

    Returns (entity_name, neo4j_label) or (None, None).
    """
    for name in _CUSTOMERS:
        if name in question:
            return name, "Customer"
    for name in _PRODUCTS:
        if name in question:
            return name, "Product"
    for name in _CATEGORIES:
        if name in question:
            return name, "Category"
    for name in _SUPPLIERS:
        if name in question:
            return name, "Supplier"
    return None, None


def _is_aggregate_question(question: str) -> bool:
    """Check if the question is an aggregate type (no specific entity anchor)."""
    return any(p.search(question) for p in _AGGREGATE_PATTERNS)


def determine_depth(question: str) -> int:
    """Determine subgraph traversal depth from question keywords."""
    if re.search(r"(직접\s*연결|1홉|직접적)", question):
        return 1
    if re.search(r"(전체\s*구조|전체\s*관계|3홉|모든\s*연결)", question):
        return 3
    return settings.local_search_default_depth


def build_subgraph_cypher(label: str, depth: int) -> str:
    """Generate subgraph extraction Cypher for given label and depth."""
    if depth == 1:
        return (
            f"MATCH (anchor:{label} {{name: $entity_name}}) "
            f"OPTIONAL MATCH (anchor)-[r1]-(n1) "
            f"RETURN anchor, labels(anchor)[0] AS anchor_label, "
            f"collect(DISTINCT {{label: labels(n1)[0], name: coalesce(n1.name, toString(id(n1))), "
            f"rel: type(r1), props: properties(n1)}}) AS hop1, "
            f"[] AS hop2"
        )
    if depth >= 3:
        return (
            f"MATCH (anchor:{label} {{name: $entity_name}}) "
            f"OPTIONAL MATCH (anchor)-[r1]-(n1) "
            f"OPTIONAL MATCH (n1)-[r2]-(n2) WHERE n2 <> anchor "
            f"OPTIONAL MATCH (n2)-[r3]-(n3) WHERE n3 <> anchor AND n3 <> n1 "
            f"RETURN anchor, labels(anchor)[0] AS anchor_label, "
            f"collect(DISTINCT {{label: labels(n1)[0], name: coalesce(n1.name, toString(id(n1))), "
            f"rel: type(r1), props: properties(n1)}}) AS hop1, "
            f"collect(DISTINCT {{label: labels(n2)[0], name: coalesce(n2.name, toString(id(n2))), "
            f"rel: type(r2), props: properties(n2)}}) AS hop2"
        )
    # depth == 2 (default)
    return (
        f"MATCH (anchor:{label} {{name: $entity_name}}) "
        f"OPTIONAL MATCH (anchor)-[r1]-(n1) "
        f"OPTIONAL MATCH (n1)-[r2]-(n2) WHERE n2 <> anchor "
        f"RETURN anchor, labels(anchor)[0] AS anchor_label, "
        f"collect(DISTINCT {{label: labels(n1)[0], name: coalesce(n1.name, toString(id(n1))), "
        f"rel: type(r1), props: properties(n1)}}) AS hop1, "
        f"collect(DISTINCT {{label: labels(n2)[0], name: coalesce(n2.name, toString(id(n2))), "
        f"rel: type(r2), props: properties(n2)}}) AS hop2"
    )


_AGGREGATE_CYPHER_MAP: dict[str, str] = {
    "category_order_count": (
        "MATCH (o:Order)-[:CONTAINS]->(p:Product)-[:BELONGS_TO]->(c:Category) "
        "RETURN c.name AS category, count(DISTINCT o) AS order_count "
        "ORDER BY order_count DESC"
    ),
    "customer_order_count": (
        "MATCH (c:Customer)-[:PLACED]->(o:Order) "
        "RETURN c.name AS customer, count(o) AS order_count "
        "ORDER BY order_count DESC"
    ),
    "avg_order_amount": (
        "MATCH (o:Order) "
        "RETURN round(avg(o.total_amount)) AS avg_amount, "
        "count(o) AS total_orders"
    ),
    "product_review_avg": (
        "MATCH (r:Review)-[:REVIEWS]->(p:Product) "
        "RETURN p.name AS product, round(avg(r.rating)*100)/100 AS avg_rating, "
        "count(r) AS review_count "
        "ORDER BY avg_rating DESC"
    ),
    "shipping_status": (
        "MATCH (s:Shipping)-[:SHIPPED_TO]->(a:Address) "
        "RETURN s.status AS status, count(s) AS count "
        "ORDER BY count DESC"
    ),
    "payment_method": (
        "MATCH (p:Payment)-[:PAID_FOR]->(o:Order) "
        "RETURN p.method AS method, count(p) AS count, "
        "round(avg(p.amount)) AS avg_amount "
        "ORDER BY count DESC"
    ),
    "coupon_comparison": (
        "MATCH (o:Order) "
        "OPTIONAL MATCH (o)-[:APPLIED]->(c:Coupon) "
        "WITH o, CASE WHEN c IS NOT NULL THEN 'used' ELSE 'unused' END AS coupon_status "
        "RETURN coupon_status, count(o) AS order_count, "
        "round(avg(o.total_amount)) AS avg_amount "
        "ORDER BY coupon_status"
    ),
}

_AGGREGATE_QUESTION_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"카테고리.*(많이|top|순위|팔린)"), "category_order_count"),
    (re.compile(r"고객별.*주문"), "customer_order_count"),
    (re.compile(r"평균.*주문.*금액|주문.*평균"), "avg_order_amount"),
    (re.compile(r"리뷰.*평점|평점.*top"), "product_review_avg"),
    (re.compile(r"배송.*상태"), "shipping_status"),
    (re.compile(r"결제.*방법|결제.*통계"), "payment_method"),
    (re.compile(r"쿠폰.*사용.*비교|쿠폰.*미사용"), "coupon_comparison"),
]


def _select_aggregate_cypher(question: str) -> str | None:
    """Select the best aggregate Cypher for a question."""
    for pattern, key in _AGGREGATE_QUESTION_MAP:
        if pattern.search(question):
            return _AGGREGATE_CYPHER_MAP.get(key)
    return None


def _execute_neo4j(cypher: str, params: dict | None = None) -> list[dict]:
    """Execute Cypher against Neo4j."""
    params = params or {}
    try:
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        with driver.session() as session:
            result = session.run(cypher, **params)
            records = [dict(r) for r in result]
        driver.close()
        return records
    except Exception as e:
        raise LocalSearchError(f"Neo4j execution failed: {e}")


def generate_answer_with_llm(
    question: str, subgraph_text: str
) -> tuple[str, list[str], int]:
    """Call OpenAI API to generate answer from subgraph context.

    Returns (answer, paths, tokens_used).
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        messages = build_local_search_messages(question, subgraph_text)

        response = client.chat.completions.create(
            model=settings.local_search_model,
            max_tokens=settings.local_search_max_tokens,
            temperature=0,
            messages=[{"role": "system", "content": LOCAL_SEARCH_SYSTEM_PROMPT}] + messages,
        )

        raw_text = response.choices[0].message.content
        tokens_used = (
            response.usage.prompt_tokens + response.usage.completion_tokens
        )

        answer, paths = parse_local_answer(raw_text)
        return answer, paths, tokens_used

    except Exception as e:
        raise LocalSearchError(f"LLM answer generation failed: {e}")


def run_local_query(question: str) -> QueryResponse:
    """B안 full pipeline: entity extract → subgraph/aggregate → LLM answer."""
    start_time = time.time()

    entity_name, entity_label = extract_entity(question)

    # Case 1: Aggregate question (no entity anchor)
    if entity_name is None and _is_aggregate_question(question):
        agg_cypher = _select_aggregate_cypher(question)
        if agg_cypher is None:
            # Generic fallback
            agg_cypher = _AGGREGATE_CYPHER_MAP["category_order_count"]

        records = _execute_neo4j(agg_cypher)
        subgraph_text = serialize_aggregate_results(records)
        answer, paths, tokens = generate_answer_with_llm(question, subgraph_text)

        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            question=question,
            answer=answer,
            cypher=agg_cypher,
            paths=paths,
            template_id="local_aggregate",
            route="local_search",
            matched_by="local_b",
            mode="b",
            subgraph_context=subgraph_text,
            llm_tokens_used=tokens,
            latency_ms=latency_ms,
        )

    # Case 2: No entity and not aggregate → unsupported
    if entity_name is None:
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            question=question,
            answer="이 질문 유형은 아직 지원하지 않습니다.",
            cypher="",
            paths=[],
            template_id="",
            route="unsupported",
            matched_by="none",
            mode="b",
            error="No entity found in question",
            latency_ms=latency_ms,
        )

    # Case 3: Entity-anchored subgraph search
    depth = determine_depth(question)
    cypher = build_subgraph_cypher(entity_label, depth)

    records = _execute_neo4j(cypher, {"entity_name": entity_name})

    if not records or records[0].get("anchor") is None:
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            question=question,
            answer=f"'{entity_name}' 엔티티를 그래프에서 찾을 수 없습니다.",
            cypher=cypher,
            paths=[],
            template_id="local_subgraph",
            route="local_search",
            matched_by="local_b",
            mode="b",
            error=f"Entity '{entity_name}' not found in graph",
            latency_ms=latency_ms,
        )

    rec = records[0]
    anchor_label = rec.get("anchor_label", entity_label)
    hop1 = rec.get("hop1", [])
    hop2 = rec.get("hop2", [])

    # Limit nodes to max_nodes
    hop1 = hop1[: settings.local_search_max_nodes]
    hop2 = hop2[: max(0, settings.local_search_max_nodes - len(hop1))]

    subgraph_text = serialize_subgraph(anchor_label, entity_name, hop1, hop2)
    answer, paths, tokens = generate_answer_with_llm(question, subgraph_text)

    latency_ms = int((time.time() - start_time) * 1000)
    return QueryResponse(
        question=question,
        answer=answer,
        cypher=cypher,
        paths=paths,
        template_id="local_subgraph",
        route="local_search",
        matched_by="local_b",
        mode="b",
        subgraph_context=subgraph_text,
        llm_tokens_used=tokens,
        latency_ms=latency_ms,
    )
