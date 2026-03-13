"""Centralized LLM usage tracker — token counts and cost estimation.

Thread-safe, in-memory. Resets on server restart.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (USD, as of 2026)
_COST_PER_1M: dict[str, tuple[float, float]] = {
    # (input_cost, output_cost)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-opus-4-6": (15.00, 75.00),
}


@dataclass
class UsageEntry:
    caller: str          # e.g. "llm_enricher", "router_llm", "local_search"
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        rates = _COST_PER_1M.get(self.model, (5.0, 15.0))
        return (self.input_tokens * rates[0] + self.output_tokens * rates[1]) / 1_000_000


class LLMUsageTracker:
    """In-memory LLM usage tracker (singleton)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[UsageEntry] = []

    def record(
        self,
        caller: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        entry = UsageEntry(
            caller=caller,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        with self._lock:
            self._entries.append(entry)
        logger.info(
            "LLM usage: caller=%s model=%s tokens=%d cost=$%.4f",
            caller, model, entry.total_tokens, entry.estimated_cost_usd,
        )
        # Also feed Prometheus counters
        try:
            from app.metrics import record_llm_usage
            record_llm_usage(caller, model, input_tokens, output_tokens)
        except Exception:
            pass

    def get_summary(self) -> dict:
        """Return aggregated usage summary."""
        with self._lock:
            entries = list(self._entries)

        total_input = sum(e.input_tokens for e in entries)
        total_output = sum(e.output_tokens for e in entries)
        total_cost = sum(e.estimated_cost_usd for e in entries)

        by_caller: dict[str, dict] = {}
        for e in entries:
            if e.caller not in by_caller:
                by_caller[e.caller] = {
                    "call_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0.0,
                }
            by_caller[e.caller]["call_count"] += 1
            by_caller[e.caller]["input_tokens"] += e.input_tokens
            by_caller[e.caller]["output_tokens"] += e.output_tokens
            by_caller[e.caller]["estimated_cost_usd"] += e.estimated_cost_usd

        by_model: dict[str, dict] = {}
        for e in entries:
            if e.model not in by_model:
                by_model[e.model] = {
                    "call_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0.0,
                }
            by_model[e.model]["call_count"] += 1
            by_model[e.model]["input_tokens"] += e.input_tokens
            by_model[e.model]["output_tokens"] += e.output_tokens
            by_model[e.model]["estimated_cost_usd"] += e.estimated_cost_usd

        return {
            "total_calls": len(entries),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "estimated_total_cost_usd": round(total_cost, 4),
            "by_caller": by_caller,
            "by_model": by_model,
        }

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()


# Global singleton
tracker = LLMUsageTracker()
