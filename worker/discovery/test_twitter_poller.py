"""
Unit tests for the Twitter/X API v2 poller stub.

Tests graceful degradation without bearer token, API response parsing,
and error handling.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from worker.discovery.twitter_poller import TwitterPoller


class TestTwitterPollerFetch:
    """Tests for TwitterPoller.fetch()."""

    @pytest.mark.asyncio
    async def test_disabled_without_bearer_token(self) -> None:
        """Returns empty list when no bearer token is set."""
        poller = TwitterPoller(bearer_token="")
        result = await poller.fetch()
        assert result == []

    @pytest.mark.asyncio
    async def test_disabled_with_none_token(self) -> None:
        """Returns empty list when bearer token is explicitly None-like."""
        poller = TwitterPoller(bearer_token="")
        result = await poller.fetch()
        assert result == []
        assert poller.source.value == "twitter"

    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_signals_from_response(self) -> None:
        """Parses tweets from API response into RawSignal instances."""
        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "123456",
                            "text": "DePIN is revolutionizing infrastructure",
                            "created_at": "2026-03-19T12:00:00Z",
                            "public_metrics": {
                                "retweet_count": 10,
                                "like_count": 50,
                                "reply_count": 5,
                            },
                        }
                    ]
                },
            )
        )

        poller = TwitterPoller(bearer_token="test-token")
        result = await poller.fetch()

        assert len(result) == 1
        assert result[0].title == "DePIN is revolutionizing infrastructure"
        assert result[0].url == "https://twitter.com/i/web/status/123456"
        assert result[0].source_metrics["likes"] == 50
        assert result[0].source_metrics["retweets"] == 10

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_api_error(self) -> None:
        """Returns empty list on API error."""
        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(429, json={"error": "rate limited"})
        )

        poller = TwitterPoller(bearer_token="test-token")
        result = await poller.fetch()
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_skips_tweets_without_text(self) -> None:
        """Skips tweets missing text field."""
        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "123", "text": "", "created_at": "2026-03-19T12:00:00Z"},
                        {"id": "456", "text": "Valid tweet", "created_at": "2026-03-19T12:00:00Z"},
                    ]
                },
            )
        )

        poller = TwitterPoller(bearer_token="test-token")
        result = await poller.fetch()
        assert len(result) == 1
        assert result[0].title == "Valid tweet"

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_data_response(self) -> None:
        """Handles response with no data field."""
        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(200, json={})
        )

        poller = TwitterPoller(bearer_token="test-token")
        result = await poller.fetch()
        assert result == []
