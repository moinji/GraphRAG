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


def _call_llm_enricher(messages: list[dict]) -> str | None:
    """Try OpenAI first, fall back to Anthropic. Returns raw text or None."""
    if settings.openai_api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=settings.openai_model,
                max_tokens=4096,
                temperature=0,
                messages=[{"role": "system", "content": CORE_SYSTEM_PROMPT}] + messages,
            )
            if response.usage:
                from app.llm_tracker import tracker
                tracker.record(
                    caller="llm_enricher",
                    model=settings.openai_model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning("OpenAI enrichment failed, trying Anthropic: %s", e)

    if settings.anthropic_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            # Convert messages to Anthropic format (system separate)
            user_messages = [m for m in messages if m.get("role") != "system"]
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=4096,
                temperature=0,
                system=CORE_SYSTEM_PROMPT,
                messages=user_messages if user_messages else messages,
            )
            if response.usage:
                from app.llm_tracker import tracker
                tracker.record(
                    caller="llm_enricher",
                    model=settings.anthropic_model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
            return response.content[0].text if response.content else None
        except Exception as e:
            logger.warning("Anthropic enrichment also failed: %s", e)

    return None


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
    if not settings.openai_api_key and not settings.anthropic_api_key:
        raise LLMEnrichmentError("No LLM API key configured (OPENAI_API_KEY or ANTHROPIC_API_KEY)")

    baseline_dict = baseline.model_dump()
    messages = build_enrichment_prompt(baseline_dict, erd_dict)

    raw_text = _call_llm_enricher(messages)

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
