"""Mode C hybrid search: vector (documents) + KG (graph) combined.

Pipeline:
    1. Vector search: embed question → pgvector similarity search
    2. KG context: extract entities from top chunks → fetch KG neighbors
    3. LLM synthesis: combine document + graph context → generate answer
    4. Source citations: document sources + KG paths

Follows project pattern: deterministic first → LLM fallback.
"""

from __future__ import annotations

import logging
import re
import time

from app.config import settings
from app.models.schemas import DocumentSource, QueryResponse
from app.query.hybrid_prompts import (
    HYBRID_SYSTEM_PROMPT,
    build_hybrid_messages,
    parse_hybrid_answer,
)
from app.query.vector_search import format_document_context, search_documents

logger = logging.getLogger(__name__)

_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")


def run_hybrid_query(
    question: str,
    tenant_id: str | None = None,
    top_k: int = 10,
    score_threshold: float = 0.3,
) -> QueryResponse:
    """Mode C full pipeline: vector search + KG context + LLM answer.

    Returns QueryResponse with document_sources populated.
    """
    start_time = time.time()
    ko = bool(_HANGUL_RE.search(question))

    # Step 1: Vector search
    vector_results = search_documents(
        question=question,
        tenant_id=tenant_id,
        top_k=top_k,
        score_threshold=score_threshold,
    )

    # Step 1.5: Rerank results (best-effort)
    try:
        from app.query.reranker import rerank
        vector_results = rerank(question, vector_results, top_k=5)
    except Exception as e:
        logger.debug("Reranking failed (non-fatal): %s", e)

    # Step 2: KG context enrichment
    graph_context = _get_kg_context(vector_results, tenant_id)

    # Step 3: Build document context
    document_context = format_document_context(vector_results, max_chunks=5)

    # No context at all → return graceful "no data" response
    if not document_context and not graph_context:
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            question=question,
            answer="관련 문서나 그래프 데이터를 찾을 수 없습니다." if ko else "No relevant documents or graph data found.",
            cypher="",
            paths=[],
            template_id="hybrid_search",
            route="hybrid",
            matched_by="hybrid_c",
            mode="c",
            error="No relevant context found",
            latency_ms=latency_ms,
            document_sources=[],
        )

    # Step 4: LLM synthesis
    answer, sources, tokens = _generate_hybrid_answer(
        question, document_context, graph_context,
    )

    # Step 5: Build document sources list
    doc_sources = _build_document_sources(vector_results)

    latency_ms = int((time.time() - start_time) * 1000)

    return QueryResponse(
        question=question,
        answer=answer,
        cypher="",
        paths=sources,
        template_id="hybrid_search",
        route="hybrid",
        matched_by="hybrid_c",
        mode="c",
        subgraph_context=graph_context if graph_context else document_context,
        llm_tokens_used=tokens,
        latency_ms=latency_ms,
        document_sources=doc_sources,
    )


def _get_kg_context(
    vector_results: list[dict],
    tenant_id: str | None = None,
) -> str:
    """Extract entities from vector results and fetch KG neighbors.

    Uses the same entity extraction pattern as local_search.py.
    Returns serialized KG context string, or empty string if no KG data.
    """
    if not vector_results:
        return ""

    try:
        from app.query.local_search import (
            _load_entities_from_neo4j,
            build_subgraph_cypher,
        )
        from app.db.neo4j_client import get_driver

        # Collect text from top chunks for entity matching
        combined_text = " ".join(r["text"] for r in vector_results[:5])

        # Load known entities from KG
        entities = _load_entities_from_neo4j(tenant_id)
        if not entities:
            return ""

        # Find entities mentioned in document chunks
        found_entities: list[tuple[str, str]] = []  # (name, label)
        for label, names in entities.items():
            for name in sorted(names, key=len, reverse=True):
                if name in combined_text and (name, label) not in found_entities:
                    found_entities.append((name, label))
                    if len(found_entities) >= 3:  # limit to top 3 entities
                        break
            if len(found_entities) >= 3:
                break

        if not found_entities:
            return ""

        # Fetch 1-hop subgraph for each found entity
        driver = get_driver()
        lines: list[str] = ["[그래프 컨텍스트]"]

        for entity_name, entity_label in found_entities:
            cypher = build_subgraph_cypher(entity_label, depth=1, tenant_id=tenant_id)
            try:
                with driver.session() as session:
                    result = session.run(cypher, entity_name=entity_name)
                    records = [dict(r) for r in result]

                if records and records[0].get("anchor") is not None:
                    rec = records[0]
                    anchor_label = rec.get("anchor_label", entity_label)
                    hop1 = rec.get("hop1", [])[:10]  # limit neighbors

                    lines.append(f"\n{anchor_label}({entity_name}):")
                    seen = set()
                    for node in hop1:
                        nlabel = node.get("label", "?")
                        nname = node.get("name", "?")
                        rel = node.get("rel", "?")
                        key = f"{nlabel}:{nname}:{rel}"
                        if key not in seen:
                            seen.add(key)
                            lines.append(f"  -{rel}-> {nlabel}({nname})")
            except Exception as e:
                logger.debug("KG context fetch failed for %s: %s", entity_name, e)

        return "\n".join(lines) if len(lines) > 1 else ""

    except Exception as e:
        logger.warning("KG context enrichment failed: %s", e)
        return ""


def _generate_hybrid_answer(
    question: str,
    document_context: str,
    graph_context: str,
) -> tuple[str, list[str], int]:
    """Call LLM to generate answer from combined context.

    Follows project pattern: OpenAI first → Anthropic fallback.
    Returns (answer, sources, tokens_used).
    """
    messages = build_hybrid_messages(question, document_context, graph_context)

    # Try OpenAI first
    if settings.openai_api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
            model = getattr(settings, "hybrid_search_model", settings.local_search_model)
            response = client.chat.completions.create(
                model=model,
                max_tokens=settings.local_search_max_tokens,
                temperature=0,
                messages=[{"role": "system", "content": HYBRID_SYSTEM_PROMPT}] + messages,
            )

            raw_text = response.choices[0].message.content or ""
            tokens = response.usage.prompt_tokens + response.usage.completion_tokens

            from app.llm_tracker import tracker
            tracker.record(
                caller="hybrid_search",
                model=model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )

            answer, sources = parse_hybrid_answer(raw_text)
            return answer, sources, tokens
        except Exception as e:
            logger.warning("OpenAI hybrid search failed, trying Anthropic: %s", e)

    # Fallback to Anthropic
    if settings.anthropic_api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.local_search_max_tokens,
                temperature=0,
                system=HYBRID_SYSTEM_PROMPT,
                messages=messages,
            )

            raw_text = response.content[0].text if response.content else ""
            tokens = response.usage.input_tokens + response.usage.output_tokens

            from app.llm_tracker import tracker
            tracker.record(
                caller="hybrid_search",
                model=settings.anthropic_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            answer, sources = parse_hybrid_answer(raw_text)
            return answer, sources, tokens
        except Exception as e:
            logger.warning("Anthropic hybrid search also failed: %s", e)

    # No LLM available → return raw context as answer
    ko = bool(_HANGUL_RE.search(question))
    fallback = (
        "LLM이 설정되지 않아 원본 컨텍스트를 반환합니다.\n\n"
        if ko else
        "No LLM configured. Returning raw context.\n\n"
    )
    context = document_context or graph_context or ""
    return fallback + context[:2000], [], 0


def _build_document_sources(vector_results: list[dict]) -> list[DocumentSource]:
    """Convert vector search results to DocumentSource models."""
    sources: list[DocumentSource] = []
    for result in vector_results[:5]:
        metadata = result.get("metadata", {})
        sources.append(DocumentSource(
            document_id=result.get("document_id", 0),
            filename=result.get("filename", "unknown"),
            chunk_text=result.get("text", "")[:500],  # truncate for response size
            relevance_score=round(result.get("score", 0.0), 3),
            page_num=metadata.get("page_num"),
            chunk_index=result.get("chunk_index", 0),
        ))
    return sources
