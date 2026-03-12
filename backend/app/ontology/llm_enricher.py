"""Stage 2: LLM ontology enrichment (via unified provider)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.exceptions import LLMEnrichmentError
from app.llm.provider import call_llm, has_any_api_key
from app.models.schemas import LLMEnrichmentDiff, OntologySpec
from app.ontology.prompts import CORE_SYSTEM_PROMPT, build_enrichment_prompt

logger = logging.getLogger(__name__)


def enrich_ontology(
    baseline: OntologySpec,
    erd_dict: dict[str, Any],
    domain_hint_text: str | None = None,
) -> tuple[OntologySpec, list[LLMEnrichmentDiff]]:
    """Call LLM to enrich the baseline ontology.

    Returns:
        Tuple of (enriched OntologySpec, list of diffs).

    Raises:
        LLMEnrichmentError: If API key is missing or API call fails.
    """
    if not has_any_api_key():
        raise LLMEnrichmentError("No LLM API key configured (OPENAI_API_KEY or ANTHROPIC_API_KEY)")

    baseline_dict = baseline.model_dump()
    messages = build_enrichment_prompt(baseline_dict, erd_dict, domain_hint_text)

    result = call_llm(messages=messages, system=CORE_SYSTEM_PROMPT, caller="llm_enricher")
    raw_text = result.text if result else None

    if raw_text is None:
        raise LLMEnrichmentError("All LLM API calls failed")

    # Parse JSON from response (strip markdown fences if present)
    json_text = raw_text.strip()
    if json_text.startswith("```"):
        lines = json_text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        json_text = "\n".join(lines)

    try:
        enriched_dict = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise LLMEnrichmentError(f"Failed to parse LLM response as JSON: {e}")

    # Validate through Pydantic
    try:
        enriched = OntologySpec(**enriched_dict)
    except Exception as e:
        raise LLMEnrichmentError(f"LLM response failed schema validation: {e}")

    # Ensure all new items have llm_suggested derivation
    baseline_rel_names = {r.name for r in baseline.relationship_types}
    for rel in enriched.relationship_types:
        if rel.name not in baseline_rel_names:
            rel.derivation = "llm_suggested"

    # Compute diffs
    diffs = _compute_diffs(baseline, enriched)

    return enriched, diffs


def _compute_diffs(
    baseline: OntologySpec,
    enriched: OntologySpec,
) -> list[LLMEnrichmentDiff]:
    """Compute differences between baseline and enriched ontology."""
    diffs: list[LLMEnrichmentDiff] = []

    baseline_node_names = {n.name for n in baseline.node_types}
    enriched_node_names = {n.name for n in enriched.node_types}

    # New nodes
    for name in enriched_node_names - baseline_node_names:
        diffs.append(LLMEnrichmentDiff(
            field="node_type",
            before=None,
            after=name,
            reason="LLM added new node type",
        ))

    # New relationships
    baseline_rel_names = {r.name for r in baseline.relationship_types}
    enriched_rel_names = {r.name for r in enriched.relationship_types}

    for name in enriched_rel_names - baseline_rel_names:
        rel = next(r for r in enriched.relationship_types if r.name == name)
        diffs.append(LLMEnrichmentDiff(
            field="relationship_type",
            before=None,
            after=f"{rel.source_node}-[{name}]->{rel.target_node}",
            reason="LLM added new relationship",
        ))

    # Removed relationships (shouldn't happen per rules, but track)
    for name in baseline_rel_names - enriched_rel_names:
        diffs.append(LLMEnrichmentDiff(
            field="relationship_type",
            before=name,
            after=None,
            reason="LLM removed relationship (unexpected)",
        ))

    return diffs
