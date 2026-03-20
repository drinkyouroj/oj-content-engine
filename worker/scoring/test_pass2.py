"""
Tests for Pass 2 LLM-assisted scoring.

Mocks the Anthropic SDK to test JSON parsing, retry logic, failure handling,
and the empty API key fallback. No network or API keys required.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.scoring.pass2 import _DEFAULT_SCORES, score_with_llm


def _make_signal(
    *,
    title: str = "Test Signal",
    body_preview: str | None = "Some preview text",
    source: str = "rss",
    source_metrics: dict | None = None,
) -> SimpleNamespace:
    """Create a fake signal for testing."""
    return SimpleNamespace(
        id="test-id",
        title=title,
        body_preview=body_preview,
        source=source,
        source_metrics=source_metrics,
    )


def _mock_anthropic_response(scores: dict) -> MagicMock:
    """Build a mock Anthropic messages.create response."""
    content_block = MagicMock()
    content_block.text = json.dumps(scores)
    response = MagicMock()
    response.content = [content_block]
    return response


@pytest.mark.asyncio
async def test_empty_api_key_returns_defaults():
    """When API key is empty, return default scores without calling the API."""
    signal = _make_signal()
    result = await score_with_llm(signal, "")
    assert result == _DEFAULT_SCORES


@pytest.mark.asyncio
async def test_successful_llm_scoring():
    """Successful API call returns parsed scores."""
    signal = _make_signal()
    expected = {
        "depth_potential": 85,
        "novelty": 70,
        "brand_angle_availability": 90,
        "brand_angle_description": "Great angle for DePIN coverage",
    }

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(expected)
    )

    with patch("worker.scoring.pass2.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await score_with_llm(signal, "sk-test-key")

    assert result == {
        "depth_potential": 85,
        "novelty": 70,
        "brand_angle_availability": 90,
    }


@pytest.mark.asyncio
async def test_scores_clamped_to_range():
    """Scores outside 0-100 are clamped."""
    signal = _make_signal()
    response_data = {
        "depth_potential": 150,
        "novelty": -10,
        "brand_angle_availability": 50,
    }

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(response_data)
    )

    with patch("worker.scoring.pass2.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await score_with_llm(signal, "sk-test-key")

    assert result["depth_potential"] == 100
    assert result["novelty"] == 0
    assert result["brand_angle_availability"] == 50


@pytest.mark.asyncio
async def test_retry_on_failure():
    """Retries up to 3 times on API failure, then returns defaults."""
    signal = _make_signal()

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        side_effect=Exception("API error")
    )

    with (
        patch("worker.scoring.pass2.anthropic.AsyncAnthropic", return_value=mock_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await score_with_llm(signal, "sk-test-key")

    assert result == _DEFAULT_SCORES
    assert mock_client.messages.create.call_count == 3


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    """If first attempt fails but second succeeds, returns scores."""
    signal = _make_signal()
    good_response = _mock_anthropic_response({
        "depth_potential": 75,
        "novelty": 60,
        "brand_angle_availability": 80,
    })

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[Exception("Transient error"), good_response]
    )

    with (
        patch("worker.scoring.pass2.anthropic.AsyncAnthropic", return_value=mock_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await score_with_llm(signal, "sk-test-key")

    assert result == {"depth_potential": 75, "novelty": 60, "brand_angle_availability": 80}
    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_invalid_json_response():
    """Invalid JSON in response triggers retry and eventual default."""
    signal = _make_signal()

    content_block = MagicMock()
    content_block.text = "not valid json"
    bad_response = MagicMock()
    bad_response.content = [content_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=bad_response)

    with (
        patch("worker.scoring.pass2.anthropic.AsyncAnthropic", return_value=mock_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await score_with_llm(signal, "sk-test-key")

    assert result == _DEFAULT_SCORES


@pytest.mark.asyncio
async def test_source_metrics_included_in_prompt():
    """Source metrics are included in the prompt when present."""
    signal = _make_signal(source_metrics={"upvotes": 150, "comments": 42})
    expected = {
        "depth_potential": 70,
        "novelty": 65,
        "brand_angle_availability": 55,
    }

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(expected)
    )

    with patch("worker.scoring.pass2.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await score_with_llm(signal, "sk-test-key")

    # Verify metrics were in the call
    call_args = mock_client.messages.create.call_args
    user_msg = call_args.kwargs["messages"][0]["content"]
    assert "upvotes" in user_msg
    assert result == expected
