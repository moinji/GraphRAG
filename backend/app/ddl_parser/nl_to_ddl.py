"""Natural language → DDL generation using LLM."""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a database schema designer. Given a natural language description of a domain,
generate a valid PostgreSQL DDL (CREATE TABLE statements with PRIMARY KEY and FOREIGN KEY).

Rules:
- Use SERIAL for auto-increment integer PKs
- Use appropriate data types (VARCHAR, INT, DECIMAL, BOOLEAN, TIMESTAMP, TEXT)
- Add NOT NULL where appropriate
- Define FOREIGN KEY references inline (column_name INT REFERENCES target_table(id))
- Include common columns like created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- Use snake_case for table and column names
- Output ONLY valid SQL DDL, no explanations or markdown fences
"""


def generate_ddl_from_nl(description: str) -> str:
    """Generate DDL SQL from natural language description using LLM.

    Tries OpenAI first, falls back to Anthropic.

    Returns:
        Generated DDL SQL string.

    Raises:
        ValueError: If no API key is configured.
        RuntimeError: If LLM call fails.
    """
    if settings.openai_api_key:
        try:
            return _call_openai(description)
        except Exception as e:
            logger.warning("OpenAI NL→DDL failed, trying Anthropic fallback: %s", e)
    if settings.anthropic_api_key:
        return _call_anthropic(description)
    raise ValueError("No LLM API key configured (OPENAI_API_KEY or ANTHROPIC_API_KEY required)")


def _call_openai(description: str) -> str:
    from openai import OpenAI

    try:
        from app.llm_tracker import track_llm_call
    except ImportError:
        track_llm_call = None

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=4096,
        temperature=0,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": description},
        ],
    )
    content = response.choices[0].message.content or ""

    if track_llm_call:
        tokens = response.usage.total_tokens if response.usage else 0
        track_llm_call("nl_to_ddl", tokens, settings.openai_model)

    return _clean_ddl(content)


def _call_anthropic(description: str) -> str:
    import anthropic

    try:
        from app.llm_tracker import track_llm_call
    except ImportError:
        track_llm_call = None

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        temperature=0,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": description}],
    )
    content = response.content[0].text if response.content else ""

    if track_llm_call:
        tokens = response.usage.input_tokens + response.usage.output_tokens
        track_llm_call("nl_to_ddl", tokens, settings.anthropic_model)

    return _clean_ddl(content)


def _clean_ddl(text: str) -> str:
    """Strip markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (``` markers)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
