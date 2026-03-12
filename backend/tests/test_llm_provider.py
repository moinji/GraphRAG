"""Tests for the unified LLM provider (app.llm.provider)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.llm.provider import LLMResponse, call_llm, has_any_api_key


# ── has_any_api_key ──────────────────────────────────────────────


@patch("app.llm.provider.settings")
def test_has_key_openai_only(mock_settings):
    mock_settings.openai_api_key = "sk-test"
    mock_settings.anthropic_api_key = ""
    assert has_any_api_key() is True


@patch("app.llm.provider.settings")
def test_has_key_anthropic_only(mock_settings):
    mock_settings.openai_api_key = ""
    mock_settings.anthropic_api_key = "ant-test"
    assert has_any_api_key() is True


@patch("app.llm.provider.settings")
def test_has_no_key(mock_settings):
    mock_settings.openai_api_key = ""
    mock_settings.anthropic_api_key = ""
    assert has_any_api_key() is False


# ── call_llm: OpenAI success ────────────────────────────────────


@patch("app.llm.provider.settings")
def test_call_llm_openai_success(mock_settings):
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-4o"
    mock_settings.anthropic_api_key = ""

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50

    mock_choice = MagicMock()
    mock_choice.message.content = "  Hello world  "

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    with patch("app.llm.provider.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = mock_response
        result = call_llm(messages=[{"role": "user", "content": "hi"}], caller="test")

    assert result is not None
    assert result.text == "Hello world"
    assert result.model == "gpt-4o"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


# ── call_llm: OpenAI fails → Anthropic fallback ─────────────────


@patch("app.llm.provider.settings")
def test_call_llm_openai_fails_anthropic_fallback(mock_settings):
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-4o"
    mock_settings.anthropic_api_key = "ant-test"
    mock_settings.anthropic_model = "claude-sonnet-4-20250514"

    mock_usage = MagicMock()
    mock_usage.input_tokens = 200
    mock_usage.output_tokens = 80

    mock_content = MagicMock()
    mock_content.text = "  Anthropic answer  "

    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_response.usage = mock_usage

    with patch("app.llm.provider.OpenAI") as MockOpenAI, \
         patch("app.llm.provider.Anthropic") as MockAnthropic:
        MockOpenAI.return_value.chat.completions.create.side_effect = Exception("OpenAI down")
        MockAnthropic.return_value.messages.create.return_value = mock_response
        result = call_llm(
            messages=[{"role": "user", "content": "hi"}],
            system="You are helpful.",
            caller="test",
        )

    assert result is not None
    assert result.text == "Anthropic answer"
    assert result.model == "claude-sonnet-4-20250514"
    assert result.input_tokens == 200
    assert result.output_tokens == 80


# ── call_llm: Both fail → None ──────────────────────────────────


@patch("app.llm.provider.settings")
def test_call_llm_both_fail_returns_none(mock_settings):
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-4o"
    mock_settings.anthropic_api_key = "ant-test"
    mock_settings.anthropic_model = "claude-sonnet-4-20250514"

    with patch("app.llm.provider.OpenAI") as MockOpenAI, \
         patch("app.llm.provider.Anthropic") as MockAnthropic:
        MockOpenAI.return_value.chat.completions.create.side_effect = Exception("fail")
        MockAnthropic.return_value.messages.create.side_effect = Exception("fail")
        result = call_llm(messages=[{"role": "user", "content": "hi"}], caller="test")

    assert result is None


# ── call_llm: No API key → None ─────────────────────────────────


@patch("app.llm.provider.settings")
def test_call_llm_no_keys_returns_none(mock_settings):
    mock_settings.openai_api_key = ""
    mock_settings.anthropic_api_key = ""

    result = call_llm(messages=[{"role": "user", "content": "hi"}], caller="test")
    assert result is None


# ── call_llm: System prompt passed correctly ─────────────────────


@patch("app.llm.provider.settings")
def test_call_llm_system_prompt_openai(mock_settings):
    """System prompt should be prepended as a system message for OpenAI."""
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-4o"
    mock_settings.anthropic_api_key = ""

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5

    mock_choice = MagicMock()
    mock_choice.message.content = "ok"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    with patch("app.llm.provider.OpenAI") as MockOpenAI:
        mock_create = MockOpenAI.return_value.chat.completions.create
        mock_create.return_value = mock_response

        call_llm(
            messages=[{"role": "user", "content": "q"}],
            system="You are a test bot.",
            caller="test",
        )

        call_args = mock_create.call_args
        msgs = call_args.kwargs["messages"]
        assert msgs[0] == {"role": "system", "content": "You are a test bot."}
        assert msgs[1] == {"role": "user", "content": "q"}


# ── call_llm: Custom model override ─────────────────────────────


@patch("app.llm.provider.settings")
def test_call_llm_model_override(mock_settings):
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-4o"
    mock_settings.anthropic_api_key = ""

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5

    mock_choice = MagicMock()
    mock_choice.message.content = "ok"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    with patch("app.llm.provider.OpenAI") as MockOpenAI:
        mock_create = MockOpenAI.return_value.chat.completions.create
        mock_create.return_value = mock_response

        result = call_llm(
            messages=[{"role": "user", "content": "q"}],
            caller="test",
            model="gpt-4o-mini",
        )

        call_args = mock_create.call_args
        assert call_args.kwargs["model"] == "gpt-4o-mini"
        assert result.model == "gpt-4o-mini"


# ── call_llm: Usage tracking ────────────────────────────────────


@patch("app.llm.provider.settings")
def test_call_llm_records_usage(mock_settings):
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-4o"
    mock_settings.anthropic_api_key = ""

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50

    mock_choice = MagicMock()
    mock_choice.message.content = "ok"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    with patch("app.llm.provider.OpenAI") as MockOpenAI, \
         patch("app.llm.provider._track") as mock_track:
        MockOpenAI.return_value.chat.completions.create.return_value = mock_response

        call_llm(messages=[{"role": "user", "content": "q"}], caller="enricher")

        mock_track.assert_called_once_with("enricher", "gpt-4o", 100, 50)


# ── call_llm: Anthropic-only (no OpenAI key) ────────────────────


@patch("app.llm.provider.settings")
def test_call_llm_anthropic_only(mock_settings):
    """When only Anthropic key exists, skip OpenAI entirely."""
    mock_settings.openai_api_key = ""
    mock_settings.anthropic_api_key = "ant-test"
    mock_settings.anthropic_model = "claude-sonnet-4-20250514"

    mock_usage = MagicMock()
    mock_usage.input_tokens = 150
    mock_usage.output_tokens = 60

    mock_content = MagicMock()
    mock_content.text = "Direct anthropic"

    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_response.usage = mock_usage

    with patch("app.llm.provider.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = mock_response
        result = call_llm(
            messages=[{"role": "user", "content": "hi"}],
            system="sys prompt",
            caller="test",
        )

    assert result is not None
    assert result.text == "Direct anthropic"
    assert result.model == "claude-sonnet-4-20250514"


@patch("app.llm.provider.settings")
def test_call_llm_anthropic_filters_system_messages(mock_settings):
    """Anthropic path should strip system role messages from the message list."""
    mock_settings.openai_api_key = ""
    mock_settings.anthropic_api_key = "ant-test"
    mock_settings.anthropic_model = "claude-sonnet-4-20250514"

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5

    mock_content = MagicMock()
    mock_content.text = "ok"

    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_response.usage = mock_usage

    with patch("app.llm.provider.Anthropic") as MockAnthropic:
        mock_create = MockAnthropic.return_value.messages.create
        mock_create.return_value = mock_response

        call_llm(
            messages=[
                {"role": "system", "content": "leaked system"},
                {"role": "user", "content": "question"},
            ],
            system="proper system",
            caller="test",
        )

        call_args = mock_create.call_args
        msgs = call_args.kwargs["messages"]
        # System messages should be filtered out
        assert all(m["role"] != "system" for m in msgs)
        assert call_args.kwargs["system"] == "proper system"


@patch("app.llm.provider.settings")
def test_call_llm_no_usage_returns_zero_tokens(mock_settings):
    """When usage is None, tokens should default to 0."""
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-4o"
    mock_settings.anthropic_api_key = ""

    mock_choice = MagicMock()
    mock_choice.message.content = "ok"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    with patch("app.llm.provider.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = mock_response
        result = call_llm(messages=[{"role": "user", "content": "q"}], caller="test")

    assert result is not None
    assert result.input_tokens == 0
    assert result.output_tokens == 0


# ── Consumer integration: enricher uses call_llm ─────────────────


@patch("app.llm.provider.settings")
def test_enricher_uses_unified_provider(mock_settings):
    """llm_enricher.enrich_ontology should use call_llm internally."""
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-4o"
    mock_settings.anthropic_api_key = ""

    from app.models.schemas import NodeType, NodeProperty, OntologySpec

    baseline = OntologySpec(
        node_types=[NodeType(name="Test", source_table="tests", properties=[
            NodeProperty(name="id", data_type="INT", source_column="id", is_key=True),
        ])],
        relationship_types=[],
    )

    # Mock call_llm at the enricher level
    mock_response = LLMResponse(
        text='{"node_types": [{"name": "Test", "source_table": "tests", "properties": [{"name": "id", "data_type": "INT", "source_column": "id", "is_key": true}]}], "relationship_types": []}',
        model="gpt-4o",
        input_tokens=100,
        output_tokens=50,
    )
    with patch("app.ontology.llm_enricher.call_llm", return_value=mock_response):
        from app.ontology.llm_enricher import enrich_ontology

        enriched, diffs = enrich_ontology(baseline, {"tables": [], "foreign_keys": []})

    assert enriched is not None
    assert len(enriched.node_types) == 1
