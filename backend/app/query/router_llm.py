"""Stage 2: LLM-based query router (OpenAI).

Falls back gracefully if API key is missing or call fails.
"""

from __future__ import annotations

import json
import logging

from app.config import settings
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


def _call_router_llm(system_prompt: str, question: str) -> str | None:
    """Try OpenAI first, fall back to Anthropic. Returns raw text or None."""
    messages = [{"role": "system", "content": system_prompt}] + _FEW_SHOT + [{"role": "user", "content": question}]

    if settings.openai_api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=settings.openai_router_model,
                max_tokens=1024,
                temperature=0,
                messages=messages,
            )
            if response.usage:
                from app.llm_tracker import tracker
                tracker.record(
                    caller="router_llm",
                    model=settings.openai_router_model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("OpenAI router failed, trying Anthropic: %s", e)

    if settings.anthropic_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            user_messages = [m for m in messages if m["role"] != "system"]
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1024,
                temperature=0,
                system=system_prompt,
                messages=user_messages,
            )
            if response.usage:
                from app.llm_tracker import tracker
                tracker.record(
                    caller="router_llm",
                    model=settings.anthropic_model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
            return response.content[0].text.strip() if response.content else None
        except Exception as e:
            logger.warning("Anthropic router also failed: %s", e)

    return None


def classify_by_llm(
    question: str, tenant_id: str | None = None,
) -> RouteResult | None:
    """Route a question using LLM with live graph schema.

    Returns (template_id, route, slots, params) or None on failure.
    Non-fatal: logs warnings instead of raising.
    """
    if not settings.openai_api_key and not settings.anthropic_api_key:
        logger.warning("LLM router skipped: no API key")
        return None

    from app.db.graph_schema import format_schema_for_prompt, get_graph_schema

    schema = get_graph_schema(tenant_id)
    schema_text = format_schema_for_prompt(schema)
    system_prompt = _SYSTEM_PROMPT.format(
        templates=list_templates_for_prompt(),
        schema=schema_text,
    )
    raw_text = _call_router_llm(system_prompt, question)
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
