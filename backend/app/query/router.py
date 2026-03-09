"""Hybrid query router: rules first, LLM fallback.

Returns (template_id, route, slots, params, matched_by).
"""

from __future__ import annotations

from app.config import settings
from app.query.router_llm import classify_by_llm
from app.query.router_rules import classify_by_rules

# (template_id, route, slots, params, matched_by)
HybridResult = tuple[str, str, dict[str, str], dict[str, object], str]


def route_question(
    question: str, tenant_id: str | None = None,
) -> HybridResult:
    """Route a question through the hybrid pipeline.

    1. Rule-based matching (fast, no API call)
    2. LLM fallback (optional, if API key configured — schema-aware)
    3. Unsupported (graceful degradation)
    """
    # Stage 1: Rules
    result = classify_by_rules(question)
    if result is not None:
        tid, route, slots, params = result
        return (tid, route, slots, params, "rule")

    # Stage 2: LLM fallback (with live graph schema)
    if settings.openai_api_key or settings.anthropic_api_key:
        result = classify_by_llm(question, tenant_id=tenant_id)
        if result is not None:
            tid, route, slots, params = result
            return (tid, route, slots, params, "llm")

    # Stage 3: Unsupported
    return ("", "unsupported", {}, {}, "none")
