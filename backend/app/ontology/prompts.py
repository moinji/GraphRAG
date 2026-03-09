"""Prompt templates for Claude LLM ontology enrichment."""

from __future__ import annotations

from typing import Any

CORE_SYSTEM_PROMPT = """\
You are an expert knowledge-graph ontologist. You receive a baseline ontology \
(generated from FK rules) and the original ERD schema. Your job is to ENRICH \
the ontology by:

1. Adding semantic relationship types that FKs cannot express \
   (e.g., RECOMMENDED, FREQUENTLY_BOUGHT_WITH).
2. Improving node/relationship naming for clarity.
3. Adding useful properties that the rule engine may have missed.
4. Fixing any obvious direction errors.

QUALITY RULES (based on Protégé ontology best practices):
- No circular references between classes (self-referential like PARENT_OF is OK).
- No duplicate class names (case-insensitive).
- All relationship source/target nodes must reference existing node types.
- Node types must be PascalCase, relationship types must be UPPER_SNAKE_CASE.
- Avoid over-segmentation: do not create too many fine-grained node types.

RULES:
- Do NOT remove any existing FK-derived nodes or relationships.
- Mark every NEW item you add with "derivation": "llm_suggested".
- Keep existing "fk_direct" and "fk_join_table" derivations unchanged.
- Return the COMPLETE ontology (baseline + your additions) as valid JSON.

OUTPUT FORMAT (strict JSON, no markdown):
{
  "node_types": [
    {
      "name": "PascalCase",
      "source_table": "table_name",
      "properties": [{"name": "col", "source_column": "col", "type": "string", "is_key": false}]
    }
  ],
  "relationship_types": [
    {
      "name": "UPPER_SNAKE",
      "source_node": "NodeA",
      "target_node": "NodeB",
      "data_table": "table_name",
      "source_key_column": "col",
      "target_key_column": "col",
      "properties": [],
      "derivation": "fk_direct | fk_join_table | llm_suggested"
    }
  ]
}
"""

GENERIC_DOMAIN_HINT = """\
Domain: Unknown / Generic.
Analyze the table names, column names, and FK relationships to infer the domain.
Only add relationships that are genuinely useful for graph queries.
Do not add speculative edges without clear query value.
"""


def build_enrichment_prompt(
    baseline: dict[str, Any],
    erd: dict[str, Any],
    domain_hint_text: str | None = None,
) -> list[dict[str, str]]:
    """Assemble the messages list for the Claude API call."""
    hint = domain_hint_text or GENERIC_DOMAIN_HINT

    user_content = (
        f"## Baseline Ontology (FK rules)\n```json\n"
        f"{_compact_json(baseline)}\n```\n\n"
        f"## Original ERD Schema\n```json\n"
        f"{_compact_json(erd)}\n```\n\n"
        f"## Domain Hint\n{hint}\n\n"
        f"Return the enriched ontology as JSON."
    )
    return [
        {"role": "user", "content": user_content},
    ]


def _compact_json(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
