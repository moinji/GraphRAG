"""Named Entity Recognition for document-to-KG linking.

2-stage NER following project pattern: rules first → LLM fallback.

Stage 1: Match text against known KG node names (exact + fuzzy).
Stage 2: LLM-based NER for entities not in KG (optional, non-fatal).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    """An entity extracted from document text."""
    name: str
    label: str           # KG node label (e.g. "Customer", "Product")
    confidence: float    # 0.0-1.0
    source: str          # "kg_match" | "llm"
    char_start: int = -1
    char_end: int = -1


def extract_entities(
    text: str,
    tenant_id: str | None = None,
    max_entities: int = 20,
) -> list[ExtractedEntity]:
    """Extract entities from text using 2-stage approach.

    Stage 1: KG node name matching (deterministic, fast)
    Stage 2: LLM NER fallback (optional, non-fatal)

    Returns list of ExtractedEntity, deduplicated by (name, label).
    """
    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()

    # Stage 1: KG-based matching
    kg_entities = _kg_match_ner(text, tenant_id)
    for ent in kg_entities:
        key = (ent.name, ent.label)
        if key not in seen and len(entities) < max_entities:
            seen.add(key)
            entities.append(ent)

    # Stage 2: LLM NER (only if we found few entities and have API key)
    if len(entities) < 3 and (settings.openai_api_key or settings.anthropic_api_key):
        try:
            llm_entities = _llm_ner(text)
            for ent in llm_entities:
                key = (ent.name, ent.label)
                if key not in seen and len(entities) < max_entities:
                    seen.add(key)
                    entities.append(ent)
        except Exception:
            logger.debug("LLM NER failed (non-fatal)", exc_info=True)

    return entities


def _kg_match_ner(
    text: str,
    tenant_id: str | None = None,
) -> list[ExtractedEntity]:
    """Stage 1: Match text against KG node names."""
    try:
        from app.query.local_search import _load_entities_from_neo4j

        entities_map = _load_entities_from_neo4j(tenant_id)
        if not entities_map:
            return []

        results: list[ExtractedEntity] = []
        text_lower = text.lower()

        for label, names in entities_map.items():
            # Sort by length descending to match longest names first
            for name in sorted(names, key=len, reverse=True):
                name_lower = name.lower()
                # Find all occurrences
                start = 0
                while True:
                    idx = text_lower.find(name_lower, start)
                    if idx == -1:
                        break
                    # Only add first occurrence per entity
                    results.append(ExtractedEntity(
                        name=name,
                        label=label,
                        confidence=1.0,
                        source="kg_match",
                        char_start=idx,
                        char_end=idx + len(name),
                    ))
                    break  # one match per entity name is enough
                    start = idx + len(name)

        # Sort by position in text
        results.sort(key=lambda e: e.char_start)
        return results

    except Exception:
        logger.debug("KG match NER failed", exc_info=True)
        return []


def _llm_ner(text: str, max_text_len: int = 3000) -> list[ExtractedEntity]:
    """Stage 2: LLM-based NER.

    Extracts named entities that might not be in the KG yet.
    """
    truncated = text[:max_text_len]

    prompt = (
        "Extract all named entities (people, organizations, products, locations, "
        "categories, dates) from the following text. "
        "Return as JSON array: [{\"name\": \"...\", \"label\": \"...\"}]\n"
        "Only return the JSON array, nothing else.\n\n"
        f"Text:\n{truncated}"
    )

    # Try OpenAI
    if settings.openai_api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=getattr(settings, "openai_router_model", "gpt-4o-mini"),
                max_tokens=500,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content or ""
            return _parse_llm_ner_response(raw)
        except Exception as e:
            logger.debug("OpenAI NER failed: %s", e)

    # Try Anthropic
    if settings.anthropic_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text if response.content else ""
            return _parse_llm_ner_response(raw)
        except Exception as e:
            logger.debug("Anthropic NER failed: %s", e)

    return []


def _parse_llm_ner_response(raw: str) -> list[ExtractedEntity]:
    """Parse LLM NER JSON response."""
    import json

    # Try to extract JSON array from response
    raw = raw.strip()
    # Find JSON array in response
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        return []

    try:
        items = json.loads(match.group())
        entities: list[ExtractedEntity] = []
        for item in items:
            if isinstance(item, dict) and "name" in item and "label" in item:
                entities.append(ExtractedEntity(
                    name=item["name"],
                    label=item["label"],
                    confidence=0.7,
                    source="llm",
                ))
        return entities
    except (json.JSONDecodeError, TypeError):
        return []
