"""Stage 2: LLM-based query router (via unified provider).

Falls back gracefully if API key is missing or call fails.
"""

from __future__ import annotations

import json
import logging

from app.config import settings
from app.llm.provider import call_llm, has_any_api_key
from app.query.template_registry import list_templates_for_prompt

logger = logging.getLogger(__name__)

# Return type: (template_id, route, slots, params)
RouteResult = tuple[str, str, dict[str, str], dict[str, object]]

_SYSTEM_PROMPT = """You are a query router for a Knowledge Graph Q&A system.
Given a user question in Korean or English, select the best Cypher template and fill the slot values.

Available templates:
{templates}

Current graph schema:
{schema}

If the schema includes "Transitive properties", a _CLOSURE relationship exists for those types.
Use the _CLOSURE relationship for ancestor/descendant queries (e.g., PARENT_OF_CLOSURE for all ancestors).
If "Inverse pairs" are listed, you can traverse relationships in either direction.
If "Inferred paths" are listed, prefer shorter path templates that use the inferred property.

Respond ONLY with a JSON object:
{{
  "template_id": "<template_id>",
  "route": "cypher_traverse" or "cypher_agg",
  "slots": {{ ... }},
  "params": {{ ... }}
}}

If no template fits, respond with:
{{
  "template_id": "",
  "route": "unsupported",
  "slots": {{}},
  "params": {{}}
}}
"""

_FEW_SHOT = [
    {
        "role": "user",
        "content": "김민수가 주문한 상품은?",
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "template_id": "two_hop",
                "route": "cypher_traverse",
                "slots": {
                    "start_label": "Customer",
                    "start_prop": "name",
                    "rel1": "PLACED",
                    "mid_label": "Order",
                    "rel2": "CONTAINS",
                    "end_label": "Product",
                    "return_prop": "name",
                },
                "params": {"val": "김민수"},
            },
            ensure_ascii=False,
        ),
    },
    {
        "role": "user",
        "content": "가장 많이 팔린 카테고리 Top 3는?",
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "template_id": "agg_with_rel",
                "route": "cypher_agg",
                "slots": {
                    "start_label": "Order",
                    "rel1": "CONTAINS",
                    "mid_label": "Product",
                    "rel2": "BELONGS_TO",
                    "end_label": "Category",
                    "group_prop": "name",
                },
                "params": {"limit": 3},
            },
            ensure_ascii=False,
        ),
    },
    {
        "role": "user",
        "content": "반품 정책은?",
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "template_id": "",
                "route": "unsupported",
                "slots": {},
                "params": {},
            },
            ensure_ascii=False,
        ),
    },
]


def classify_by_llm(
    question: str, tenant_id: str | None = None,
) -> RouteResult | None:
    """Route a question using LLM with live graph schema.

    Returns (template_id, route, slots, params) or None on failure.
    Non-fatal: logs warnings instead of raising.
    """
    if not has_any_api_key():
        logger.warning("LLM router skipped: no API key")
        return None

    from app.db.graph_schema import format_schema_for_prompt, get_graph_schema

    schema = get_graph_schema(tenant_id)
    schema_text = format_schema_for_prompt(schema)
    system_prompt = _SYSTEM_PROMPT.format(
        templates=list_templates_for_prompt(),
        schema=schema_text,
    )
    messages = _FEW_SHOT + [{"role": "user", "content": question}]
    result = call_llm(
        messages=messages,
        system=system_prompt,
        caller="router_llm",
        model=settings.openai_router_model,
        max_tokens=1024,
    )
    raw_text = result.text if result else None
    if raw_text is None:
        return None

    # Strip markdown fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        raw_text = "\n".join(lines)

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("LLM router returned invalid JSON: %s", raw_text[:200])
        return None

    template_id = result.get("template_id", "")
    route = result.get("route", "unsupported")
    slots = result.get("slots", {})
    params = result.get("params", {})

    if not template_id or route == "unsupported":
        return None

    return (template_id, route, slots, params)
