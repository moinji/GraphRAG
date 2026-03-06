"""LLM tracker unit tests."""

from app.llm_tracker import LLMUsageTracker


def test_tracker_record_and_summary():
    """Record entries and verify summary aggregation."""
    t = LLMUsageTracker()
    t.record("local_search", "gpt-4o", 500, 200)
    t.record("router_llm", "gpt-4o-mini", 300, 50)
    t.record("local_search", "gpt-4o", 400, 150)

    s = t.get_summary()
    assert s["total_calls"] == 3
    assert s["total_input_tokens"] == 1200
    assert s["total_output_tokens"] == 400
    assert s["total_tokens"] == 1600

    assert s["by_caller"]["local_search"]["call_count"] == 2
    assert s["by_caller"]["router_llm"]["call_count"] == 1
    assert s["by_model"]["gpt-4o"]["call_count"] == 2
    assert s["by_model"]["gpt-4o-mini"]["call_count"] == 1

    assert s["estimated_total_cost_usd"] > 0


def test_tracker_reset():
    """Reset clears all entries."""
    t = LLMUsageTracker()
    t.record("test", "gpt-4o", 100, 50)
    t.reset()
    s = t.get_summary()
    assert s["total_calls"] == 0
    assert s["total_tokens"] == 0


def test_tracker_cost_estimation():
    """Cost is calculated from known model rates."""
    t = LLMUsageTracker()
    # gpt-4o: $2.50/1M input, $10.00/1M output
    t.record("test", "gpt-4o", 1_000_000, 0)
    s = t.get_summary()
    assert abs(s["estimated_total_cost_usd"] - 2.50) < 0.01

    t.reset()
    t.record("test", "gpt-4o", 0, 1_000_000)
    s = t.get_summary()
    assert abs(s["estimated_total_cost_usd"] - 10.00) < 0.01
