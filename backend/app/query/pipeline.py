"""Q&A pipeline: route → slot fill → execute → answer.

Orchestrates the full question-answering flow.
"""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict

from app.db.neo4j_client import get_driver
from app.exceptions import CypherExecutionError
from app.models.schemas import QueryResponse
from app.query.router import route_question
from app.query.slot_filler import fill_template
from app.query.template_registry import get_template

logger = logging.getLogger(__name__)

_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")

# ── LRU cache for Mode A deterministic queries ──────────────────
_QUERY_CACHE_MAX = 128
_query_cache: OrderedDict[tuple[str, str | None], QueryResponse] = OrderedDict()


def _cache_get(question: str, tenant_id: str | None) -> QueryResponse | None:
    key = (question, tenant_id)
    if key in _query_cache:
        _query_cache.move_to_end(key)
        return _query_cache[key]
    return None


def _cache_put(question: str, tenant_id: str | None, response: QueryResponse) -> None:
    key = (question, tenant_id)
    _query_cache[key] = response
    _query_cache.move_to_end(key)
    while len(_query_cache) > _QUERY_CACHE_MAX:
        _query_cache.popitem(last=False)


def invalidate_query_cache(tenant_id: str | None = None) -> None:
    """Clear query cache — call after KG rebuild."""
    if tenant_id is None:
        _query_cache.clear()
    else:
        to_remove = [k for k in _query_cache if k[1] == tenant_id]
        for k in to_remove:
            del _query_cache[k]


def _is_korean(text: str) -> bool:
    """Return True if the text contains Korean characters."""
    return bool(_HANGUL_RE.search(text))


def run_query_stream(
    question: str, tenant_id: str | None = None,
):
    """Streaming Mode A pipeline — yields SSE event dicts.

    Yields:
        {"_event": "metadata", "route": ..., "template_id": ..., "matched_by": ...}
        {"_event": "complete", **QueryResponse fields}
    """
    start_time = time.time()

    # Demo cache → immediate complete
    if tenant_id is None:
        from app.query.demo_cache import get_cached_answer

        cached = get_cached_answer(question)
        if cached is not None:
            yield {"_event": "complete", **cached.model_dump()}
            return

    # LRU cache → immediate complete
    lru_hit = _cache_get(question, tenant_id)
    if lru_hit is not None:
        yield {"_event": "complete", **lru_hit.model_dump()}
        return

    # 1. Route
    template_id, route, slots, params, matched_by = route_question(question, tenant_id=tenant_id)

    # Yield routing metadata
    yield {
        "_event": "metadata",
        "template_id": template_id,
        "route": route,
        "matched_by": matched_by,
        "mode": "a",
    }

    # Unsupported → early complete
    if route == "unsupported":
        latency_ms = int((time.time() - start_time) * 1000)
        unsupported_msg = (
            "이 질문 유형은 아직 지원하지 않습니다."
            if _is_korean(question)
            else "This question type is not yet supported."
        )
        yield {
            "_event": "complete",
            **QueryResponse(
                question=question,
                answer=unsupported_msg,
                cypher="",
                paths=[],
                template_id="",
                route="unsupported",
                matched_by="none",
                error="No matching template found",
                mode="a",
                latency_ms=latency_ms,
            ).model_dump(),
        }
        return

    # 2-6: Slot fill → Cypher → Neo4j → paths → answer → node IDs
    cypher, neo4j_params = fill_template(template_id, slots, params)
    records = _execute_cypher(cypher, neo4j_params)
    paths = _extract_paths(records, template_id, slots, params)
    answer = _generate_answer(question, records, template_id, slots, params)
    related_node_ids = _extract_related_node_ids(records, template_id, slots, params)

    latency_ms = int((time.time() - start_time) * 1000)
    response = QueryResponse(
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

    _cache_put(question, tenant_id, response)
    yield {"_event": "complete", **response.model_dump()}


def run_query(
    question: str, mode: str = "a", tenant_id: str | None = None,
) -> QueryResponse:
    """Execute the full Q&A pipeline for a single question."""
    start_time = time.time()

    # C안: hybrid search pipeline (vector + KG)
    if mode == "c":
        from app.query.hybrid_search import run_hybrid_query

        return run_hybrid_query(question, tenant_id=tenant_id)

    # B안: local search pipeline
    if mode == "b":
        from app.query.local_search import run_local_query

        return run_local_query(question, tenant_id=tenant_id)

    # A안: check demo cache first (skip in multi-tenant mode)
    if tenant_id is None:
        from app.query.demo_cache import get_cached_answer

        cached = get_cached_answer(question)
        if cached is not None:
            return cached

    # A안: LRU cache check
    lru_hit = _cache_get(question, tenant_id)
    if lru_hit is not None:
        return lru_hit

    # A안: template-based pipeline
    # 1. Route (pass tenant_id for schema-aware LLM fallback)
    template_id, route, slots, params, matched_by = route_question(question, tenant_id=tenant_id)

    # Unsupported → early return
    if route == "unsupported":
        latency_ms = int((time.time() - start_time) * 1000)
        unsupported_msg = (
            "이 질문 유형은 아직 지원하지 않습니다."
            if _is_korean(question)
            else "This question type is not yet supported."
        )
        return QueryResponse(
            question=question,
            answer=unsupported_msg,
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
    response = QueryResponse(
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

    # Cache successful Mode A results
    _cache_put(question, tenant_id, response)
    return response


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

    elif template_id == "property_lookup":
        for rec in records:
            val = rec.get("result", "?")
            paths.append(f"{slots.get('label', '?')}({params.get('val', '?')}).{slots.get('return_prop', '?')} = {val}")

    elif template_id == "reverse_two_hop":
        name = params.get("val", "?")
        for rec in records:
            val = rec.get("result", "?")
            paths.append(f"{slots.get('end_label', '?')}({val}) -> ... -> {slots.get('start_label', '?')}({name})")

    elif template_id == "count_all":
        for rec in records:
            total = rec.get("total", "?")
            paths.append(f"{slots.get('label', '?')}: {total}")

    elif template_id == "group_count":
        for rec in records:
            cat = rec.get("category", "?")
            cnt = rec.get("cnt", "?")
            paths.append(f"{cat}: {cnt}")

    elif template_id == "max_prop":
        for rec in records:
            name = rec.get("name", "?")
            value = rec.get("value", "?")
            paths.append(f"{name}: {value}")

    return paths


def _generate_answer(
    question: str,
    records: list[dict],
    template_id: str,
    slots: dict[str, str],
    params: dict[str, object],
) -> str:
    """Generate an answer from query results, matching the question language."""
    ko = _is_korean(question)

    if not records:
        return "해당 조건에 맞는 결과가 없습니다." if ko else "No results found for the given criteria."

    if template_id == "two_hop":
        items = [r.get("result", "") for r in records]
        name = params.get("val", "?")
        end_label = slots.get("end_label", "항목")
        if ko:
            return f"{name}의 {end_label}: {', '.join(str(i) for i in items)}"
        return f"{end_label} for {name}: {', '.join(str(i) for i in items)}"

    if template_id == "custom_q2":
        name = params.get("name", "?")
        lines = []
        for i, r in enumerate(records, 1):
            if ko:
                lines.append(f"{i}위 {r['product']}({r['category']}, 평점 {r['avg_rating']})")
            else:
                lines.append(f"#{i} {r['product']} ({r['category']}, rating {r['avg_rating']})")
        if ko:
            return f"{name}가 주문한 상품 카테고리 내 리뷰 평점 Top {len(records)}: {', '.join(lines)}"
        return f"Top {len(records)} rated products in categories ordered by {name}: {', '.join(lines)}"

    if template_id == "agg_with_rel":
        lines = []
        for i, r in enumerate(records, 1):
            if ko:
                lines.append(f"{i}위 {r['category']}({r['order_count']}건)")
            else:
                lines.append(f"#{i} {r['category']} ({r['order_count']} orders)")
        if ko:
            return f"가장 많이 팔린 카테고리 Top {len(records)}: {', '.join(lines)}"
        return f"Top {len(records)} best-selling categories: {', '.join(lines)}"

    if template_id == "custom_q5":
        parts = []
        for r in records:
            if ko:
                status_label = "쿠폰 사용" if r.get("coupon_status") == "used" else "쿠폰 미사용"
                parts.append(f"{status_label}: {r.get('order_count', 0)}건, 평균 {r.get('avg_amount', 0)}원")
            else:
                status_label = "Coupon used" if r.get("coupon_status") == "used" else "No coupon"
                parts.append(f"{status_label}: {r.get('order_count', 0)} orders, avg {r.get('avg_amount', 0)}")
        return " | ".join(parts)

    if template_id == "top_n":
        lines = []
        for i, r in enumerate(records, 1):
            if ko:
                lines.append(f"{i}위 {r.get('category', '?')}({r.get('cnt', 0)}건)")
            else:
                lines.append(f"#{i} {r.get('category', '?')} ({r.get('cnt', 0)})")
        return f"Top {len(records)}: {', '.join(lines)}"

    if template_id == "custom_q4":
        products = [r.get("product", "") for r in records]
        if ko:
            return f"공통 구매 상품: {', '.join(str(p) for p in products)}"
        return f"Common products: {', '.join(str(p) for p in products)}"

    if template_id in ("one_hop_out", "one_hop_in", "filtered", "status_filter"):
        items = [str(r.get("result", "")) for r in records]
        if ko:
            return f"결과: {', '.join(items)}"
        return f"Results: {', '.join(items)}"

    if template_id == "three_hop":
        items = [str(r.get("result", "")) for r in records]
        name = params.get("val", "?")
        end_label = slots.get("end_label", "항목")
        if ko:
            return f"{name}의 {end_label}: {', '.join(items)}"
        return f"{end_label} for {name}: {', '.join(items)}"

    if template_id == "common_neighbor":
        items = [str(r.get("result", "")) for r in records]
        if ko:
            return f"공통 항목: {', '.join(items)}"
        return f"Common items: {', '.join(items)}"

    if template_id == "shortest_path":
        for r in records:
            path_nodes = r.get("path_nodes", [])
            if ko:
                return f"최단 경로: {' -> '.join(str(n) for n in path_nodes)}"
            return f"Shortest path: {' -> '.join(str(n) for n in path_nodes)}"

    if template_id == "property_lookup":
        val = str(records[0].get("result", ""))
        entity = params.get("val", "?")
        prop = slots.get("return_prop", "?")
        if ko:
            return f"{entity}의 {prop}: {val}"
        return f"{entity}'s {prop}: {val}"

    if template_id == "reverse_two_hop":
        items = [str(r.get("result", "")) for r in records]
        anchor = params.get("val", "?")
        end_label = slots.get("end_label", "항목")
        if ko:
            return f"{anchor} 관련 {end_label}: {', '.join(items)}"
        return f"{end_label} related to {anchor}: {', '.join(items)}"

    if template_id == "count_all":
        total = records[0].get("total", 0)
        label = slots.get("label", "?")
        if ko:
            return f"총 {label} 수: {total}"
        return f"Total {label} count: {total}"

    if template_id == "group_count":
        lines = []
        for i, r in enumerate(records, 1):
            cat = r.get("category", "?")
            cnt = r.get("cnt", 0)
            if ko:
                lines.append(f"{cat}: {cnt}건")
            else:
                lines.append(f"{cat}: {cnt}")
        if ko:
            return f"그룹별 수: {', '.join(lines)}"
        return f"Count by group: {', '.join(lines)}"

    if template_id == "max_prop":
        name = records[0].get("name", "?")
        value = records[0].get("value", "?")
        if ko:
            return f"가장 높은 항목: {name} ({value})"
        return f"Top item: {name} ({value})"

    # Fallback: generic answer
    if ko:
        return f"조회 결과 {len(records)}건이 있습니다."
    return f"Found {len(records)} result(s)."


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

    elif template_id == "reverse_two_hop":
        start_label = slots.get("start_label", "")
        end_label = slots.get("end_label", "")
        anchor_val = str(params.get("val", ""))
        result_vals = [str(r.get("result", "")) for r in records if r.get("result")]
        if start_label and anchor_val:
            lookups.append((start_label, "name", [anchor_val]))
        if end_label and result_vals:
            lookups.append((end_label, "name", result_vals))

    elif template_id == "property_lookup":
        label = slots.get("label", "")
        anchor_val = str(params.get("val", ""))
        if label and anchor_val:
            lookups.append((label, "name", [anchor_val]))

    elif template_id == "three_hop":
        start_label = slots.get("start_label", "")
        end_label = slots.get("end_label", "")
        anchor_val = str(params.get("val", ""))
        result_vals = [str(r.get("result", "")) for r in records if r.get("result")]
        if start_label and anchor_val:
            lookups.append((start_label, "name", [anchor_val]))
        if end_label and result_vals:
            lookups.append((end_label, "name", result_vals))

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
