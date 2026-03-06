"""Stage 2: OpenAI API ontology enrichment."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.exceptions import LLMEnrichmentError
from app.models.schemas import LLMEnrichmentDiff, OntologySpec
from app.ontology.prompts import CORE_SYSTEM_PROMPT, build_enrichment_prompt

logger = logging.getLogger(__name__)


def enrich_ontology(
    baseline: OntologySpec,
    erd_dict: dict[str, Any],
) -> tuple[OntologySpec, list[LLMEnrichmentDiff]]:
    """Call OpenAI to enrich the baseline ontology.

    Returns:
        Tuple of (enriched OntologySpec, list of diffs).

    Raises:
        LLMEnrichmentError: If API key is missing or API call fails.
    """
    if not settings.openai_api_key:
        raise LLMEnrichmentError("OPENAI_API_KEY not configured")

    try:
        from openai import OpenAI
    except ImportError:
        raise LLMEnrichmentError("openai package not installed")

    baseline_dict = baseline.model_dump()
    messages = build_enrichment_prompt(baseline_dict, erd_dict)

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=4096,
            temperature=0,
            messages=[{"role": "system", "content": CORE_SYSTEM_PROMPT}] + messages,
        )
    except Exception as e:
        raise LLMEnrichmentError(f"OpenAI API call failed: {e}")

    # Track token usage
    if response.usage:
        from app.llm_tracker import tracker
        tracker.record(
            caller="llm_enricher",
            model=settings.openai_model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )

    # Extract text content
    raw_text = response.choices[0].message.content

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
