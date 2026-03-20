"""Tests for thesis suggestion generation."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.generation.thesis_suggestions import suggest_theses, _parse_theses, _fetch_article
from worker.generation.llm_client import LLMResponse


def _make_topic():
    topic = MagicMock()
    topic.id = uuid.uuid4()
    topic.thesis = None

    signal = MagicMock()
    signal.title = "AI Safety Theater Problem"
    signal.url = "https://example.com/article"
    signal.body_preview = "A deep dive into AI safety frameworks that don't work"
    signal.source_metrics = {"upvotes": 200}

    scored_signal = MagicMock()
    scored_signal.composite_score = 72.0
    scored_signal.score_breakdown = {
        "signal_strength": 80, "timing_window": 70, "depth_potential": 75,
        "novelty": 65, "community_resonance": 60, "brand_angle_availability": 85,
    }
    scored_signal.signal = signal

    topic.scored_signal = scored_signal
    return topic


class TestParseTheses:
    def test_parses_numbered_list(self):
        raw = "1. First thesis here.\n2. Second thesis here.\n3. Third thesis."
        result = _parse_theses(raw)
        assert len(result) == 3
        assert result[0] == "First thesis here."
        assert result[2] == "Third thesis."

    def test_parses_with_extra_whitespace(self):
        raw = "1.  First thesis.\n\n2.  Second thesis.\n\n3.  Third thesis."
        result = _parse_theses(raw)
        assert len(result) == 3

    def test_fallback_on_unparseable(self):
        raw = "Here is a single thesis about the topic."
        result = _parse_theses(raw)
        assert len(result) == 1
        assert result[0] == raw.strip()

    def test_strips_numbering(self):
        raw = "1. First thesis.\n2. Second thesis.\n3. Third thesis."
        result = _parse_theses(raw)
        assert not result[0].startswith("1")


class TestFetchArticle:
    @pytest.mark.asyncio
    async def test_returns_text_on_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><article><p>Article content here.</p></article></body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("worker.generation.thesis_suggestions.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            text = await _fetch_article("https://example.com/article")
            assert "Article content" in text

    @pytest.mark.asyncio
    async def test_returns_empty_on_failure(self):
        with patch("worker.generation.thesis_suggestions.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=Exception("timeout"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            text = await _fetch_article("https://example.com/bad")
            assert text == ""


class TestSuggestTheses:
    @pytest.mark.asyncio
    async def test_returns_thesis_list(self):
        topic = _make_topic()
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="1. AI safety frameworks are theater.\n2. Regulation without enforcement.\n3. The compliance industrial complex.",
            total_tokens=300,
            model="claude-haiku-4-5",
            provider="anthropic",
        ))

        with patch("worker.generation.thesis_suggestions._fetch_article", return_value="Full article text here"):
            result = await suggest_theses(topic, mock_client)

        assert len(result) == 3
        assert "theater" in result[0].lower()
        mock_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_body_preview(self):
        topic = _make_topic()
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="1. Thesis one.\n2. Thesis two.\n3. Thesis three.",
            total_tokens=200,
            model="claude-haiku-4-5",
            provider="anthropic",
        ))

        with patch("worker.generation.thesis_suggestions._fetch_article", return_value=""):
            result = await suggest_theses(topic, mock_client)

        assert len(result) == 3
        call_kwargs = mock_client.generate.call_args.kwargs
        assert "AI safety frameworks" in call_kwargs["user_prompt"]
