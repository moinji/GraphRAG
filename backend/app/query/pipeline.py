"""Q&A pipeline: route → slot fill → execute → answer.

Orchestrates the full question-answering flow.
"""

from __future__ import annotations

import logging
import time

from app.db.neo4j_client import get_driver
from app.exceptions import CypherExecutionError
from app.models.schemas import QueryResponse
from app.query.router import route_question
from app.query.slot_filler import fill_template
from app.query.template_registry import get_template

logger = logging.getLogger(__name__)


def run_query(question: str, mode: str = "a") -> QueryResponse:
    """Execute the full Q&A pipeline for a single question."""
    start_time = time.time()

    # B안: local search pipeline
    if mode == "b":
        from app.query.local_search import run_local_query

        return run_local_query(question)

    # A안: check demo cache first
    from app.query.demo_cache import get_cached_answer

    cached = get_cached_answer(question)
    if cached is not None:
        return cached

    # A안: template-based pipeline
    # 1. Route
    template_id, route, slots, params, matched_by = route_question(question)

    # Unsupported → early return
    if route == "unsupported":
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            question=question,
            answer="이 질문 유형은 아직 지원하지 않습니다.",
            cypher="",
            paths=[],
            template_id="",
            route="unsupported",
            matched_by="none",
            error="No matching template found",
            mode="a",
            latency_ms=latency_ms,
        )

    # 2. Slot fill → Cypher
    cypher, neo4j_params = fill_template(template_id, slots, params)

    # 3. Execute against Neo4j
    records = _execute_cypher(cypher, neo4j_params)

    # 4. Extract evidence paths
    paths = _extract_paths(records, template_id, slots, params)

    # 5. Generate answer
    answer = _generate_answer(question, records, template_id, slots, params)

    # 6. Extract related node IDs for graph highlighting
    related_node_ids = _extract_related_node_ids(records, template_id, slots, params)

    latency_ms = int((time.time() - start_time) * 1000)
    return QueryResponse(
        question=question,
        answer=answer,
        cypher=cypher,
        paths=paths,
        template_id=template_id,
        route=route,
        matched_by=matched_by,
        error=None,
        mode="a",
        latency_ms=latency_ms,
        related_node_ids=related_node_ids,
    )


def _execute_cypher(cypher: str, params: dict[str, object]) -> list[dict]:
    """Run Cypher against Neo4j and return list of record dicts."""
    try:
        driver = get_driver()
        with driver.session() as session:
            result = session.run(cypher, **params)
            records = [dict(r) for r in result]
        return records
    except Exception as e:
        raise CypherExecutionError(f"Neo4j execution failed: {e}")


def _extract_paths(
    records: list[dict],
    template_id: str,
    slots: dict[str, str],
    params: dict[str, object],
) -> list[str]:
    """Build human-readable evidence paths from query results."""
    paths: list[str] = []

    if template_id == "two_hop":
        name = params.get("val", "?")
        start = slots.get("start_label", "?")
        rel1 = slots.get("rel1", "?")
        mid = slots.get("mid_label", "?")
        rel2 = slots.get("rel2", "?")
        end = slots.get("end_label", "?")
        for rec in records:
            val = rec.get("result", "?")
            paths.append(f"{start}({name}) -> {rel1} -> {mid} -> {rel2} -> {end}({val})")

    elif template_id == "custom_q2":
        name = params.get("name", "?")
        for rec in records:
            product = rec.get("product", "?")
            category = rec.get("category", "?")
            rating = rec.get("avg_rating", "?")
            paths.append(
                f"Customer({name}) -> PLACED -> Order -> CONTAINS -> Product(*) "
                f"-> BELONGS_TO -> Category({category}) "
                f"<- BELONGS_TO <- Product({product}) "
                f"<- REVIEWS <- Review [avg={rating}]"
            )

    elif template_id == "agg_with_rel":
        for rec in records:
            cat = rec.get("category", "?")
            cnt = rec.get("order_count", "?")
            paths.append(
                f"Order(*) -> CONTAINS -> Product(*) "
                f"-> BELONGS_TO -> Category({cat}) [count={cnt}]"
            )

    elif template_id == "custom_q5":
        for rec in records:
            status = rec.get("coupon_status", "?")
            cnt = rec.get("order_count", "?")
            avg_amt = rec.get("avg_amount", "?")
            paths.append(
                f"Order(*) -> APPLIED -> Coupon [status={status}, count={cnt}, avg={avg_amt}]"
            )

    elif template_id in ("one_hop_out", "one_hop_in", "filtered", "status_filter"):
        for rec in records:
            val = rec.get("result", "?")
            paths.append(f"{val}")

    elif template_id == "top_n":
        for rec in records:
            cat = rec.get("category", "?")
            cnt = rec.get("cnt", "?")
            paths.append(f"{cat} [count={cnt}]")

    elif template_id == "three_hop":
        name = params.get("val", "?")
        for rec in records:
            val = rec.get("result", "?")
            paths.append(f"{slots.get('start_label', '?')}({name}) -> ... -> {slots.get('end_label', '?')}({val})")

    elif template_id == "shortest_path":
        for rec in records:
            path_nodes = rec.get("path_nodes", [])
            paths.append(" -> ".join(str(n) for n in path_nodes))

    elif template_id == "common_neighbor":
        for rec in records:
            val = rec.get("result", "?")
            paths.append(f"{val}")

    elif template_id == "custom_q4":
        for rec in records:
            product = rec.get("product", "?")
            paths.append(f"Product({product})")

    return paths


def _generate_answer(
    question: str,
    records: list[dict],
    template_id: str,
    slots: dict[str, str],
    params: dict[str, object],
) -> str:
    """Generate a Korean-language answer from query results."""
    if not records:
        return "해당 조건에 맞는 결과가 없습니다."

    if template_id == "two_hop":
        items = [r.get("result", "") for r in records]
        name = params.get("val", "?")
        return f"{name} 고객이 주문한 상품: {', '.join(str(i) for i in items)}"

    if template_id == "custom_q2":
        name = params.get("name", "?")
        lines = []
        for i, r in enumerate(records, 1):
            lines.append(f"{i}위 {r['product']}({r['category']}, 평점 {r['avg_rating']})")
        return f"{name}가 주문한 상품 카테고리 내 리뷰 평점 Top {len(records)}: {', '.join(lines)}"

    if template_id == "agg_with_rel":
        lines = []
        for i, r in enumerate(records, 1):
            lines.append(f"{i}위 {r['category']}({r['order_count']}건)")
        return f"가장 많이 팔린 카테고리 Top {len(records)}: {', '.join(lines)}"

    if template_id == "custom_q5":
        parts = []
        for r in records:
            status_label = "쿠폰 사용" if r.get("coupon_status") == "used" else "쿠폰 미사용"
            parts.append(f"{status_label}: {r.get('order_count', 0)}건, 평균 {r.get('avg_amount', 0)}원")
        return " | ".join(parts)

    if template_id == "top_n":
        lines = []
        for i, r in enumerate(records, 1):
            lines.append(f"{i}위 {r.get('category', '?')}({r.get('cnt', 0)}건)")
        return f"Top {len(records)}: {', '.join(lines)}"

    if template_id == "custom_q4":
        products = [r.get("product", "") for r in records]
        return f"공통 구매 상품: {', '.join(str(p) for p in products)}"

    if template_id in ("one_hop_out", "one_hop_in", "filtered", "status_filter"):
        items = [str(r.get("result", "")) for r in records]
        return f"결과: {', '.join(items)}"

    if template_id == "three_hop":
        items = [str(r.get("result", "")) for r in records]
        return f"결과: {', '.join(items)}"

    if template_id == "common_neighbor":
        items = [str(r.get("result", "")) for r in records]
        return f"공통 항목: {', '.join(items)}"

    if template_id == "shortest_path":
        for r in records:
            path_nodes = r.get("path_nodes", [])
            return f"최단 경로: {' -> '.join(str(n) for n in path_nodes)}"

    # Fallback: generic answer
    return f"조회 결과 {len(records)}건이 있습니다."


def _extract_related_node_ids(
    records: list[dict],
    template_id: str,
    slots: dict[str, str],
    params: dict[str, object],
) -> list[str]:
    """Build a list of lookups from query results, then resolve to composite node IDs."""
    # Each lookup: (label, property_name, values)
    lookups: list[tuple[str, str, list[str]]] = []

    if template_id == "two_hop":
        # Anchor: start entity; Results: end entities
        start_label = slots.get("start_label", "")
        end_label = slots.get("end_label", "")
        anchor_val = str(params.get("val", ""))
        result_vals = [str(r.get("result", "")) for r in records if r.get("result")]
        if start_label and anchor_val:
            lookups.append((start_label, "name", [anchor_val]))
        if end_label and result_vals:
            lookups.append((end_label, "name", result_vals))

    elif template_id == "custom_q2":
        # Anchor: Customer; Results: Product + Category
        anchor_name = str(params.get("name", ""))
        if anchor_name:
            lookups.append(("Customer", "name", [anchor_name]))
        products = [str(r.get("product", "")) for r in records if r.get("product")]
        categories = [str(r.get("category", "")) for r in records if r.get("category")]
        if products:
            lookups.append(("Product", "name", products))
        if categories:
            lookups.append(("Category", "name", categories))

    elif template_id == "agg_with_rel":
        # Results: end_label entities (categories)
        end_label = slots.get("end_label", "Category")
        cats = [str(r.get("category", "")) for r in records if r.get("category")]
        if cats:
            lookups.append((end_label, "name", cats))

    elif template_id == "custom_q4":
        # Two customers + common products
        name1 = str(params.get("name1", ""))
        name2 = str(params.get("name2", ""))
        customers = [n for n in [name1, name2] if n]
        if customers:
            lookups.append(("Customer", "name", customers))
        products = [str(r.get("product", "")) for r in records if r.get("product")]
        if products:
            lookups.append(("Product", "name", products))

    elif template_id == "custom_q5":
        # Aggregate query — no specific nodes
        return []

    else:
        return []

    if not lookups:
        return []

    return _batch_resolve_node_ids(lookups)


def _batch_resolve_node_ids(
    lookups: list[tuple[str, str, list[str]]],
) -> list[str]:
    """Resolve (label, prop, values) tuples to composite node IDs via Neo4j."""
    try:
        driver = get_driver()
        result_ids: list[str] = []
        with driver.session() as session:
            for label, prop, vals in lookups:
                cypher = f"MATCH (n:{label}) WHERE n.{prop} IN $vals RETURN n.id AS nid"
                records = session.run(cypher, vals=vals)
                for rec in records:
                    nid = rec.get("nid")
                    if nid is not None:
                        composite = f"{label}_{nid}"
                        if composite not in result_ids:
                            result_ids.append(composite)
        return result_ids
    except Exception as e:
        logger.warning("Failed to resolve related node IDs: %s", e)
        return []
