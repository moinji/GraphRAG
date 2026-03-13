"""Text2Cypher pipeline (Mode D): NL → Cypher → Neo4j → answer.

Generates Cypher from natural language using LLM with live graph schema,
validates for safety, executes, and synthesizes a human-readable answer.
"""

from __future__ import annotations

import logging
import re
import time

from app.circuit_breaker import neo4j_breaker
from app.config import settings
from app.db.graph_schema import format_schema_for_prompt, get_graph_schema
from app.db.neo4j_client import get_driver
from app.llm.provider import call_llm, has_any_api_key
from app.models.schemas import QueryResponse
from app.query.text2cypher_prompts import (
    TEXT2CYPHER_ANSWER_SYSTEM,
    TEXT2CYPHER_SYSTEM,
    build_answer_messages,
    build_cypher_messages,
)

logger = logging.getLogger(__name__)

_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")

# ── Cypher validation ─────────────────────────────────────────────

# Deny-list: destructive or write operations
_CYPHER_DENY_RE = re.compile(
    r"""
    (?:^|\s)(?:
        DELETE|
        DETACH\s+DELETE|
        DROP\b|
        REMOVE\s+\w+|
        MERGE\b|
        LOAD\s+CSV|
        FOREACH\b|
        CREATE\s+INDEX|
        CREATE\s+CONSTRAINT
    )
    |
    \bSET\s+\w+\s*[\.\:]
    |
    (?:^|\s)CREATE\s+\(
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MAX_CYPHER_LENGTH = 2000


def validate_cypher(cypher: str) -> tuple[bool, str | None]:
    """Validate generated Cypher for safety.

    Returns (is_valid, error_message).
    """
    if not cypher or not cypher.strip():
        return False, "Empty Cypher query"

    cypher_upper = cypher.upper().strip()

    # Must contain MATCH or CALL (for read-only procedures)
    if "MATCH" not in cypher_upper and "CALL" not in cypher_upper:
        return False, "Cypher must contain MATCH or CALL"

    # Must contain RETURN
    if "RETURN" not in cypher_upper:
        return False, "Cypher must contain RETURN"

    # Length limit
    if len(cypher) > _MAX_CYPHER_LENGTH:
        return False, f"Cypher exceeds maximum length ({_MAX_CYPHER_LENGTH} chars)"

    # No multiple statements (semicolons outside quotes)
    # Simple check: count semicolons not inside quotes
    clean = re.sub(r"'[^']*'|\"[^\"]*\"", "", cypher)
    if ";" in clean:
        return False, "Multiple statements not allowed"

    # Deny-list check
    if _CYPHER_DENY_RE.search(cypher):
        return False, "Write operations are not allowed (DELETE/CREATE/MERGE/SET/DROP/REMOVE)"

    return True, None


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences that LLMs sometimes add."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        text = re.sub(r"^```\w*\n?", "", text)
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


# ── Pipeline ──────────────────────────────────────────────────────

def run_text2cypher_query(
    question: str, tenant_id: str | None = None,
) -> QueryResponse:
    """Execute Text2Cypher pipeline: schema → LLM generate → validate → execute → answer."""
    start_time = time.time()
    ko = bool(_HANGUL_RE.search(question))
    total_tokens = 0

    # 1. Check API key
    if not has_any_api_key():
        return QueryResponse(
            question=question,
            answer="LLM API 키가 설정되지 않았습니다." if ko else "No LLM API key configured.",
            cypher="",
            mode="d",
            route="text2cypher",
            matched_by="none",
            error="no_api_key",
            latency_ms=int((time.time() - start_time) * 1000),
        )

    # 2. Fetch live graph schema
    schema = get_graph_schema(tenant_id)
    schema_text = format_schema_for_prompt(schema)
    if not schema.get("node_labels"):
        return QueryResponse(
            question=question,
            answer="그래프 스키마가 비어있습니다. 먼저 KG를 빌드하세요." if ko else "Graph schema is empty. Build a KG first.",
            cypher="",
            mode="d",
            route="text2cypher",
            matched_by="none",
            error="empty_schema",
            latency_ms=int((time.time() - start_time) * 1000),
        )

    # 3. Generate Cypher via LLM
    messages = build_cypher_messages(question, schema_text)
    gen_result = call_llm(
        messages=messages,
        system=TEXT2CYPHER_SYSTEM,
        caller="text2cypher_generate",
        model=settings.text2cypher_model,
        max_tokens=settings.text2cypher_max_tokens,
        temperature=0,
    )

    if gen_result is None:
        return QueryResponse(
            question=question,
            answer="Cypher 생성에 실패했습니다." if ko else "Failed to generate Cypher.",
            cypher="",
            mode="d",
            route="text2cypher",
            matched_by="llm_cypher",
            error="llm_generation_failed",
            latency_ms=int((time.time() - start_time) * 1000),
        )

    cypher = _strip_markdown_fences(gen_result.text)
    total_tokens += gen_result.input_tokens + gen_result.output_tokens

    # 4. Validate
    is_valid, validation_error = validate_cypher(cypher)
    if not is_valid:
        return QueryResponse(
            question=question,
            answer=f"생성된 Cypher가 안전하지 않습니다: {validation_error}" if ko
                   else f"Generated Cypher failed validation: {validation_error}",
            cypher=cypher,
            mode="d",
            route="text2cypher",
            matched_by="llm_cypher",
            error=f"validation_failed: {validation_error}",
            llm_tokens_used=total_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
        )

    # 5. Execute against Neo4j
    try:
        records = _execute_cypher(cypher)
    except Exception as e:
        return QueryResponse(
            question=question,
            answer=f"Cypher 실행 오류: {e}" if ko else f"Cypher execution error: {e}",
            cypher=cypher,
            mode="d",
            route="text2cypher",
            matched_by="llm_cypher",
            error=f"execution_failed: {e}",
            llm_tokens_used=total_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
        )

    # 6. Synthesize answer via LLM
    answer_messages = build_answer_messages(question, cypher, records)
    answer_result = call_llm(
        messages=answer_messages,
        system=TEXT2CYPHER_ANSWER_SYSTEM,
        caller="text2cypher_answer",
        model=settings.text2cypher_model,
        max_tokens=1024,
        temperature=0,
    )

    if answer_result is not None:
        answer = answer_result.text
        total_tokens += answer_result.input_tokens + answer_result.output_tokens
    else:
        # Fallback: format results directly
        if not records:
            answer = "해당 조건에 맞는 결과가 없습니다." if ko else "No results found."
        else:
            lines = []
            for rec in records[:10]:
                parts = [f"{k}: {v}" for k, v in rec.items()]
                lines.append(", ".join(parts))
            answer = "\n".join(lines)

    # 7. Extract paths from results
    paths = _extract_paths(records)

    latency_ms = int((time.time() - start_time) * 1000)
    return QueryResponse(
        question=question,
        answer=answer,
        cypher=cypher,
        paths=paths,
        template_id="",
        route="text2cypher",
        matched_by="llm_cypher",
        error=None,
        mode="d",
        llm_tokens_used=total_tokens,
        latency_ms=latency_ms,
    )


def _execute_cypher(cypher: str) -> list[dict]:
    """Execute read-only Cypher against Neo4j with circuit breaker."""
    if not neo4j_breaker.allow_request():
        raise RuntimeError("Neo4j circuit breaker is OPEN")

    try:
        driver = get_driver()
        with driver.session() as session:
            result = session.run(cypher)
            records = [dict(r) for r in result]
        neo4j_breaker.record_success()
        return records
    except Exception as e:
        neo4j_breaker.record_failure()
        raise RuntimeError(f"Neo4j execution failed: {e}") from e


def _extract_paths(records: list[dict], max_paths: int = 10) -> list[str]:
    """Build simple evidence paths from raw query results."""
    paths: list[str] = []
    for rec in records[:max_paths]:
        parts = [f"{k}={v}" for k, v in rec.items() if v is not None]
        if parts:
            paths.append(", ".join(parts))
    return paths
