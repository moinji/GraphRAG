"""B안 Local Search: entity extraction → subgraph → LLM answer.

Self-implemented GraphRAG local search (no Microsoft dependency).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import AsyncGenerator

from app.config import settings
from app.db.neo4j_client import get_driver
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

# ── Fallback entities from seed data ────────────────────────────
_FALLBACK_ENTITIES: dict[str, set[str]] = {
    "Customer": {"김민수", "이영희", "박지훈", "최수진", "정대현"},
    "Product": {
        "맥북프로", "에어팟프로", "갤럭시탭", "LG그램", "갤럭시버즈",
        "아이패드에어", "맥북에어", "소니WH-1000XM5",
    },
    "Category": {"전자기기", "의류", "식품", "노트북", "오디오", "태블릿"},
    "Supplier": {"애플코리아", "삼성전자", "LG전자"},
}

# Dynamic entity cache (populated from Neo4j), keyed by tenant_id
_entity_cache: dict[str | None, dict[str, set[str]]] = {}
_entity_cache_ts: dict[str | None, float] = {}
_ENTITY_CACHE_TTL = 300  # 5 minutes


def _load_entities_from_neo4j(tenant_id: str | None = None) -> dict[str, set[str]]:
    """Query Neo4j for all node labels and their name properties."""
    from app.tenant import tenant_label_prefix

    now = time.time()
    cached = _entity_cache.get(tenant_id)
    cached_ts = _entity_cache_ts.get(tenant_id, 0.0)
    if cached is not None and (now - cached_ts) < _ENTITY_CACHE_TTL:
        return cached

    prefix = tenant_label_prefix(tenant_id)

    try:
        driver = get_driver()
        entities: dict[str, set[str]] = {}
        with driver.session() as session:
            if prefix:
                # Only load entities with tenant-prefixed labels
                result = session.run(
                    "MATCH (n) WHERE n.name IS NOT NULL "
                    "WITH n, [l IN labels(n) WHERE l STARTS WITH $prefix][0] AS lbl "
                    "WHERE lbl IS NOT NULL "
                    "RETURN lbl AS label, collect(DISTINCT n.name) AS names",
                    prefix=prefix,
                )
            else:
                result = session.run(
                    "MATCH (n) WHERE n.name IS NOT NULL "
                    "RETURN labels(n)[0] AS label, collect(DISTINCT n.name) AS names"
                )
            for record in result:
                label = record["label"]
                # Strip tenant prefix for entity matching
                if prefix and label.startswith(prefix):
                    label = label[len(prefix):]
                names = set(record["names"])
                if names:
                    entities[label] = names
        if not entities:
            # Neo4j is empty (no data loaded yet), use fallback
            return _FALLBACK_ENTITIES
        _entity_cache[tenant_id] = entities
        _entity_cache_ts[tenant_id] = now
        logger.debug("Loaded %d entity types from Neo4j (tenant=%s)", len(entities), tenant_id)
        return entities
    except Exception:
        logger.warning("Failed to load entities from Neo4j, using fallback", exc_info=True)
        return _FALLBACK_ENTITIES


def invalidate_entity_cache(tenant_id: str | None = None) -> None:
    """Clear the entity cache (call after KG rebuild)."""
    if tenant_id is not None:
        _entity_cache.pop(tenant_id, None)
        _entity_cache_ts.pop(tenant_id, None)
    else:
        _entity_cache.clear()
        _entity_cache_ts.clear()


# Aggregate question patterns (no specific entity anchor)
_AGGREGATE_PATTERNS = [
    re.compile(r"(가장|많이|top|순위|평균|총|합계|통계|전체)", re.IGNORECASE),
    re.compile(r"(카테고리별|고객별|상품별|월별|주문별)", re.IGNORECASE),
    re.compile(r"(몇\s*개|몇\s*명|몇\s*건)", re.IGNORECASE),
    # English aggregate patterns
    re.compile(r"(most|total|average|ranking|statistics|overall|how\s*many)", re.IGNORECASE),
    re.compile(r"(by\s+category|by\s+customer|by\s+product|per\s+month)", re.IGNORECASE),
]


def extract_entity(
    question: str, tenant_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Extract the main entity from a question.

    Dynamically loads entity names from Neo4j (with TTL cache).
    Falls back to hardcoded seed data if Neo4j is unavailable.
    Returns (entity_name, neo4j_label) or (None, None).
    """
    entities = _load_entities_from_neo4j(tenant_id)
    for label, names in entities.items():
        for name in sorted(names, key=len, reverse=True):  # longest match first
            if name in question:
                return name, label
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


def build_subgraph_cypher(label: str, depth: int, tenant_id: str | None = None) -> str:
    """Generate subgraph extraction Cypher for given label and depth."""
    from app.tenant import prefixed_label
    label = prefixed_label(tenant_id, label)
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


def _select_aggregate_cypher(
    question: str, tenant_id: str | None = None,
) -> str | None:
    """Select the best aggregate Cypher for a question."""
    for pattern, key in _AGGREGATE_QUESTION_MAP:
        if pattern.search(question):
            cypher = _AGGREGATE_CYPHER_MAP.get(key)
            if cypher and tenant_id is not None:
                from app.tenant import prefix_cypher_labels
                known = list(_FALLBACK_ENTITIES.keys()) + [
                    "Order", "Product", "Category", "Customer", "Review",
                    "Shipping", "Address", "Payment", "Coupon", "Supplier",
                ]
                cypher = prefix_cypher_labels(cypher, tenant_id, known)
            return cypher
    return None


def _execute_neo4j(cypher: str, params: dict | None = None) -> list[dict]:
    """Execute Cypher against Neo4j."""
    params = params or {}
    try:
        driver = get_driver()
        with driver.session() as session:
            result = session.run(cypher, **params)
            records = [dict(r) for r in result]
        return records
    except Exception as e:
        raise LocalSearchError(f"Neo4j execution failed: {e}")


def generate_answer_with_llm(
    question: str, subgraph_text: str
) -> tuple[str, list[str], int]:
    """Call LLM to generate answer from subgraph context.

    Tries OpenAI first, falls back to Anthropic.
    Returns (answer, paths, tokens_used).
    """
    messages = build_local_search_messages(question, subgraph_text)

    # Try OpenAI first
    if settings.openai_api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
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

            from app.llm_tracker import tracker
            tracker.record(
                caller="local_search",
                model=settings.local_search_model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )

            answer, paths = parse_local_answer(raw_text)
            return answer, paths, tokens_used
        except Exception as e:
            logger.warning("OpenAI local search failed, trying Anthropic: %s", e)

    # Fallback to Anthropic
    if settings.anthropic_api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.local_search_max_tokens,
                temperature=0,
                system=LOCAL_SEARCH_SYSTEM_PROMPT,
                messages=messages,
            )

            raw_text = response.content[0].text if response.content else ""
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            from app.llm_tracker import tracker
            tracker.record(
                caller="local_search",
                model=settings.anthropic_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            answer, paths = parse_local_answer(raw_text)
            return answer, paths, tokens_used
        except Exception as e:
            raise LocalSearchError(f"LLM answer generation failed: {e}")

    raise LocalSearchError("No LLM API key configured for local search")


def run_local_query(
    question: str, tenant_id: str | None = None,
) -> QueryResponse:
    """B안 full pipeline: entity extract → subgraph/aggregate → LLM answer."""
    start_time = time.time()

    entity_name, entity_label = extract_entity(question, tenant_id)

    # Case 1: Aggregate question (no entity anchor)
    if entity_name is None and _is_aggregate_question(question):
        agg_cypher = _select_aggregate_cypher(question, tenant_id)
        if agg_cypher is None:
            # Generic fallback
            agg_cypher = _AGGREGATE_CYPHER_MAP["category_order_count"]
            if tenant_id is not None:
                from app.tenant import prefix_cypher_labels
                known = ["Order", "Product", "Category", "Customer"]
                agg_cypher = prefix_cypher_labels(agg_cypher, tenant_id, known)

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
        _ko = bool(re.search(r"[\uac00-\ud7a3]", question))
        return QueryResponse(
            question=question,
            answer="이 질문 유형은 아직 지원하지 않습니다." if _ko else "This question type is not yet supported.",
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
    cypher = build_subgraph_cypher(entity_label, depth, tenant_id)

    records = _execute_neo4j(cypher, {"entity_name": entity_name})

    if not records or records[0].get("anchor") is None:
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            question=question,
            answer=(
                f"'{entity_name}' 엔티티를 그래프에서 찾을 수 없습니다."
                if re.search(r"[\uac00-\ud7a3]", question)
                else f"Entity '{entity_name}' not found in the graph."
            ),
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


# ── Streaming variants ───────────────────────────────────────────


async def _stream_llm_tokens(
    question: str, subgraph_text: str,
) -> AsyncGenerator[str, None]:
    """Stream LLM answer tokens via asyncio.Queue bridging sync→async."""
    messages = build_local_search_messages(question, subgraph_text)
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _sync_stream() -> tuple[int, int]:
        """Run synchronous LLM streaming in a thread, push tokens to queue."""
        input_tokens = 0
        output_tokens = 0

        if settings.openai_api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=settings.openai_api_key)
                response = client.chat.completions.create(
                    model=settings.local_search_model,
                    max_tokens=settings.local_search_max_tokens,
                    temperature=0,
                    messages=[{"role": "system", "content": LOCAL_SEARCH_SYSTEM_PROMPT}] + messages,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        queue.put_nowait(chunk.choices[0].delta.content)
                    if chunk.usage:
                        input_tokens = chunk.usage.prompt_tokens
                        output_tokens = chunk.usage.completion_tokens
                queue.put_nowait(None)
                return input_tokens, output_tokens
            except Exception as e:
                logger.warning("OpenAI streaming failed, trying Anthropic: %s", e)

        if settings.anthropic_api_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                with client.messages.stream(
                    model=settings.anthropic_model,
                    max_tokens=settings.local_search_max_tokens,
                    temperature=0,
                    system=LOCAL_SEARCH_SYSTEM_PROMPT,
                    messages=messages,
                ) as stream:
                    for text in stream.text_stream:
                        queue.put_nowait(text)
                    msg = stream.get_final_message()
                    input_tokens = msg.usage.input_tokens
                    output_tokens = msg.usage.output_tokens
                queue.put_nowait(None)
                return input_tokens, output_tokens
            except Exception as e:
                queue.put_nowait(None)
                raise LocalSearchError(f"LLM streaming failed: {e}")

        queue.put_nowait(None)
        raise LocalSearchError("No LLM API key configured for local search")

    loop = asyncio.get_event_loop()
    task = loop.run_in_executor(None, _sync_stream)

    while True:
        token = await queue.get()
        if token is None:
            break
        yield token

    # Get usage from completed task
    result = await task
    # Store usage in a way accessible to caller
    _stream_llm_tokens._last_usage = result  # type: ignore[attr-defined]


async def run_local_query_stream(
    question: str, tenant_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Streaming B안 pipeline: yields metadata → tokens → complete."""
    start_time = time.time()

    entity_name, entity_label = extract_entity(question, tenant_id)

    # Case 1: Aggregate question
    if entity_name is None and _is_aggregate_question(question):
        agg_cypher = _select_aggregate_cypher(question, tenant_id)
        if agg_cypher is None:
            agg_cypher = _AGGREGATE_CYPHER_MAP["category_order_count"]
            if tenant_id is not None:
                from app.tenant import prefix_cypher_labels
                known = ["Order", "Product", "Category", "Customer"]
                agg_cypher = prefix_cypher_labels(agg_cypher, tenant_id, known)

        records = _execute_neo4j(agg_cypher)
        subgraph_text = serialize_aggregate_results(records)

        yield {"_event": "metadata", "cypher": agg_cypher, "template_id": "local_aggregate",
               "route": "local_search", "subgraph_context": subgraph_text}

        full_answer = ""
        async for token in _stream_llm_tokens(question, subgraph_text):
            full_answer += token
            yield {"_event": "token", "token": token}

        usage = getattr(_stream_llm_tokens, "_last_usage", (0, 0))
        tokens = usage[0] + usage[1]
        answer, paths = parse_local_answer(full_answer)
        latency_ms = int((time.time() - start_time) * 1000)

        yield {"_event": "complete", "question": question, "answer": answer,
               "cypher": agg_cypher, "paths": paths, "template_id": "local_aggregate",
               "route": "local_search", "matched_by": "local_b", "mode": "b",
               "subgraph_context": subgraph_text, "llm_tokens_used": tokens,
               "latency_ms": latency_ms}
        return

    # Case 2: No entity and not aggregate
    if entity_name is None:
        latency_ms = int((time.time() - start_time) * 1000)
        _ko = bool(re.search(r"[\uac00-\ud7a3]", question))
        yield {"_event": "complete", "question": question,
               "answer": "이 질문 유형은 아직 지원하지 않습니다." if _ko else "This question type is not yet supported.",
               "cypher": "", "paths": [], "template_id": "", "route": "unsupported",
               "matched_by": "none", "mode": "b", "error": "No entity found in question",
               "latency_ms": latency_ms}
        return

    # Case 3: Entity-anchored subgraph search
    depth = determine_depth(question)
    cypher = build_subgraph_cypher(entity_label, depth, tenant_id)
    records = _execute_neo4j(cypher, {"entity_name": entity_name})

    if not records or records[0].get("anchor") is None:
        latency_ms = int((time.time() - start_time) * 1000)
        _ko = bool(re.search(r"[\uac00-\ud7a3]", question))
        yield {"_event": "complete", "question": question,
               "answer": f"'{entity_name}' 엔티티를 그래프에서 찾을 수 없습니다." if _ko else f"Entity '{entity_name}' not found in the graph.",
               "cypher": cypher, "paths": [], "template_id": "local_subgraph",
               "route": "local_search", "matched_by": "local_b", "mode": "b",
               "error": f"Entity '{entity_name}' not found in graph",
               "latency_ms": latency_ms}
        return

    rec = records[0]
    anchor_label = rec.get("anchor_label", entity_label)
    hop1 = rec.get("hop1", [])
    hop2 = rec.get("hop2", [])
    hop1 = hop1[: settings.local_search_max_nodes]
    hop2 = hop2[: max(0, settings.local_search_max_nodes - len(hop1))]

    subgraph_text = serialize_subgraph(anchor_label, entity_name, hop1, hop2)

    yield {"_event": "metadata", "cypher": cypher, "template_id": "local_subgraph",
           "route": "local_search", "subgraph_context": subgraph_text}

    full_answer = ""
    async for token in _stream_llm_tokens(question, subgraph_text):
        full_answer += token
        yield {"_event": "token", "token": token}

    usage = getattr(_stream_llm_tokens, "_last_usage", (0, 0))
    tokens = usage[0] + usage[1]
    answer, paths = parse_local_answer(full_answer)
    latency_ms = int((time.time() - start_time) * 1000)

    yield {"_event": "complete", "question": question, "answer": answer,
           "cypher": cypher, "paths": paths, "template_id": "local_subgraph",
           "route": "local_search", "matched_by": "local_b", "mode": "b",
           "subgraph_context": subgraph_text, "llm_tokens_used": tokens,
           "latency_ms": latency_ms}
