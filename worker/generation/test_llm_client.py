"""
Tests for the unified LLM client abstraction.

Mocks both Groq and Anthropic SDKs to test generation, retry logic,
code fence stripping, env-var model overrides, and missing API key handling.
No network or API keys required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.generation.llm_client import (
    GENERATION_MODELS,
    LLMClient,
    LLMGenerationError,
    LLMResponse,
    get_model_config,
)


# ---------------------------------------------------------------------------
# get_model_config
# ---------------------------------------------------------------------------


def test_get_model_config_returns_default():
    """Returns the built-in config for a known platform."""
    cfg = get_model_config("substack")
    assert cfg["provider"] == "groq"
    assert cfg["model"] == "llama-3.3-70b-versatile"


def test_get_model_config_env_override(monkeypatch):
    """Env var GENERATION_MODEL_<PLATFORM> overrides the default config."""
    monkeypatch.setenv("GENERATION_MODEL_TWITTER", "anthropic/claude-3-5-haiku-20241022")
    cfg = get_model_config("twitter")
    assert cfg["provider"] == "anthropic"
    assert cfg["model"] == "claude-3-5-haiku-20241022"


def test_get_model_config_env_override_uppercase(monkeypatch):
    """Env var lookup is case-insensitive for the platform name."""
    monkeypatch.setenv("GENERATION_MODEL_LINKEDIN", "groq/llama-3.1-8b-instant")
    cfg = get_model_config("linkedin")
    assert cfg["provider"] == "groq"
    assert cfg["model"] == "llama-3.1-8b-instant"


def test_substack_critique_key_exists():
    """substack_critique key is present in GENERATION_MODELS."""
    assert "substack_critique" in GENERATION_MODELS
    cfg = GENERATION_MODELS["substack_critique"]
    assert "provider" in cfg
    assert "model" in cfg


def test_unknown_platform_raises_key_error():
    """Unknown platform raises KeyError."""
    with pytest.raises(KeyError):
        get_model_config("tiktok")


# ---------------------------------------------------------------------------
# Groq generation
# ---------------------------------------------------------------------------


def _mock_groq_response(content: str, input_tokens: int = 50, output_tokens: int = 100) -> MagicMock:
    """Build a mock Groq chat.completions.create response."""
    usage = MagicMock()
    usage.total_tokens = input_tokens + output_tokens
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


@pytest.mark.asyncio
async def test_groq_generation_success():
    """Successful Groq call returns an LLMResponse with correct fields."""
    mock_groq_instance = AsyncMock()
    mock_groq_instance.chat.completions.create = AsyncMock(
        return_value=_mock_groq_response("Hello from Groq")
    )

    with patch("worker.generation.llm_client.AsyncGroq", return_value=mock_groq_instance):
        client = LLMClient(groq_api_key="gsk-test")
        result = await client.generate(
            system_prompt="You are a writer.",
            user_prompt="Write something.",
            provider="groq",
            model="llama-3.3-70b-versatile",
        )

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello from Groq"
    assert result.provider == "groq"
    assert result.model == "llama-3.3-70b-versatile"
    assert result.total_tokens == 150


@pytest.mark.asyncio
async def test_groq_generation_strips_code_fences():
    """Code fences are stripped from Groq response content."""
    raw = "```json\n{\"key\": \"value\"}\n```"
    mock_groq_instance = AsyncMock()
    mock_groq_instance.chat.completions.create = AsyncMock(
        return_value=_mock_groq_response(raw)
    )

    with patch("worker.generation.llm_client.AsyncGroq", return_value=mock_groq_instance):
        client = LLMClient(groq_api_key="gsk-test")
        result = await client.generate(
            system_prompt="sys",
            user_prompt="user",
            provider="groq",
            model="llama-3.3-70b-versatile",
        )

    assert result.content == '{"key": "value"}'


# ---------------------------------------------------------------------------
# Anthropic generation
# ---------------------------------------------------------------------------


def _mock_anthropic_response(content: str, input_tokens: int = 40, output_tokens: int = 80) -> MagicMock:
    """Build a mock Anthropic messages.create response."""
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    text_block = MagicMock()
    text_block.text = content
    response = MagicMock()
    response.content = [text_block]
    response.usage = usage
    return response


@pytest.mark.asyncio
async def test_anthropic_generation_success():
    """Successful Anthropic call returns an LLMResponse with correct fields."""
    mock_anthropic_instance = AsyncMock()
    mock_anthropic_instance.messages.create = AsyncMock(
        return_value=_mock_anthropic_response("Hello from Anthropic")
    )
    mock_anthropic_cls = MagicMock(return_value=mock_anthropic_instance)

    with patch.dict("sys.modules", {"anthropic": MagicMock(AsyncAnthropic=mock_anthropic_cls)}):
        client = LLMClient(anthropic_api_key="sk-ant-test")
        result = await client.generate(
            system_prompt="You are a writer.",
            user_prompt="Write something.",
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
        )

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello from Anthropic"
    assert result.provider == "anthropic"
    assert result.model == "claude-3-5-haiku-20241022"
    assert result.total_tokens == 120


@pytest.mark.asyncio
async def test_anthropic_generation_strips_code_fences():
    """Code fences are stripped from Anthropic response content."""
    raw = "```python\nprint('hello')\n```"
    mock_anthropic_instance = AsyncMock()
    mock_anthropic_instance.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(raw)
    )
    mock_anthropic_cls = MagicMock(return_value=mock_anthropic_instance)

    with patch.dict("sys.modules", {"anthropic": MagicMock(AsyncAnthropic=mock_anthropic_cls)}):
        client = LLMClient(anthropic_api_key="sk-ant-test")
        result = await client.generate(
            system_prompt="sys",
            user_prompt="user",
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
        )

    assert result.content == "print('hello')"


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_failure_raises_llm_generation_error():
    """Exhausting all retries raises LLMGenerationError."""
    mock_groq_instance = AsyncMock()
    mock_groq_instance.chat.completions.create = AsyncMock(
        side_effect=Exception("Transient API error")
    )

    with (
        patch("worker.generation.llm_client.AsyncGroq", return_value=mock_groq_instance),
        patch("asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(LLMGenerationError),
    ):
        client = LLMClient(groq_api_key="gsk-test")
        await client.generate(
            system_prompt="sys",
            user_prompt="user",
            provider="groq",
            model="llama-3.3-70b-versatile",
            max_retries=3,
        )

    assert mock_groq_instance.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    """If the first attempt fails but the second succeeds, returns the result."""
    good_response = _mock_groq_response("Success on retry")
    mock_groq_instance = AsyncMock()
    mock_groq_instance.chat.completions.create = AsyncMock(
        side_effect=[Exception("First failure"), good_response]
    )

    with (
        patch("worker.generation.llm_client.AsyncGroq", return_value=mock_groq_instance),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        client = LLMClient(groq_api_key="gsk-test")
        result = await client.generate(
            system_prompt="sys",
            user_prompt="user",
            provider="groq",
            model="llama-3.3-70b-versatile",
            max_retries=3,
        )

    assert result.content == "Success on retry"
    assert mock_groq_instance.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# Missing API key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_groq_api_key_raises_llm_generation_error():
    """Missing Groq API key raises LLMGenerationError immediately."""
    client = LLMClient(groq_api_key="")
    with pytest.raises(LLMGenerationError, match="[Gg]roq"):
        await client.generate(
            system_prompt="sys",
            user_prompt="user",
            provider="groq",
            model="llama-3.3-70b-versatile",
        )


@pytest.mark.asyncio
async def test_missing_anthropic_api_key_raises_llm_generation_error():
    """Missing Anthropic API key raises LLMGenerationError immediately."""
    client = LLMClient(anthropic_api_key="")
    with pytest.raises(LLMGenerationError, match="[Aa]nthropic"):
        await client.generate(
            system_prompt="sys",
            user_prompt="user",
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
        )


@pytest.mark.asyncio
async def test_unknown_provider_raises_llm_generation_error():
    """Unknown provider string raises LLMGenerationError."""
    client = LLMClient(groq_api_key="gsk-test")
    with pytest.raises(LLMGenerationError, match="[Uu]nknown"):
        await client.generate(
            system_prompt="sys",
            user_prompt="user",
            provider="openai",
            model="gpt-4o",
        )
