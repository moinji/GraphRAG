"""Unified LLM provider with OpenAI → Anthropic fallback.

Replaces duplicated if/else branches across llm_enricher, router_llm, local_search, etc.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

# Guarded imports — available only when the SDK is installed
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore[assignment,misc]


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def call_llm(
    *,
    messages: list[dict],
    system: str | None = None,
    caller: str = "unknown",
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0,
) -> LLMResponse | None:
    """Call LLM with OpenAI → Anthropic fallback.

    Args:
        messages: List of {"role": "user"/"assistant", "content": "..."} dicts.
        system: System prompt (injected as system role for OpenAI, system param for Anthropic).
        caller: Identifier for usage tracking (e.g. "llm_enricher", "router_llm").
        model: Override model name. If None, uses settings defaults per provider.
        max_tokens: Maximum output tokens.
        temperature: Sampling temperature.

    Returns:
        LLMResponse or None if all providers fail.
    """
    # Try OpenAI first
    result = _try_openai(
        messages=messages,
        system=system,
        model=model or settings.openai_model,
        max_tokens=max_tokens,
        temperature=temperature,
        caller=caller,
    )
    if result is not None:
        return result

    # Fall back to Anthropic
    result = _try_anthropic(
        messages=messages,
        system=system,
        model=model or settings.anthropic_model,
        max_tokens=max_tokens,
        temperature=temperature,
        caller=caller,
    )
    return result


def has_any_api_key() -> bool:
    """Check if at least one LLM API key is configured."""
    return bool(settings.openai_api_key or settings.anthropic_api_key)


def _try_openai(
    *,
    messages: list[dict],
    system: str | None,
    model: str,
    max_tokens: int,
    temperature: float,
    caller: str,
) -> LLMResponse | None:
    if not settings.openai_api_key or OpenAI is None:
        return None
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=full_messages,
        )
        text = response.choices[0].message.content or ""
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        _track(caller, model, input_tokens, output_tokens)
        return LLMResponse(
            text=text.strip(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception as e:
        logger.warning("OpenAI call failed (%s), trying Anthropic: %s", caller, e)
        return None


def _try_anthropic(
    *,
    messages: list[dict],
    system: str | None,
    model: str,
    max_tokens: int,
    temperature: float,
    caller: str,
) -> LLMResponse | None:
    if not settings.anthropic_api_key or Anthropic is None:
        return None
    try:
        client = Anthropic(api_key=settings.anthropic_api_key)
        # Anthropic: system is a separate param, messages must not contain system role
        user_messages = [m for m in messages if m.get("role") != "system"]
        if not user_messages:
            user_messages = messages

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "",
            messages=user_messages,
        )
        text = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens if response.usage else 0
        output_tokens = response.usage.output_tokens if response.usage else 0

        _track(caller, model, input_tokens, output_tokens)
        return LLMResponse(
            text=text.strip(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception as e:
        logger.warning("Anthropic call also failed (%s): %s", caller, e)
        return None


def _track(caller: str, model: str, input_tokens: int, output_tokens: int) -> None:
    """Record usage to the global tracker (best-effort)."""
    try:
        from app.llm_tracker import tracker

        tracker.record(
            caller=caller,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception:
        pass
