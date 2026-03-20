"""
Unit tests for the Reddit poller.

Uses respx to mock httpx responses and test JSON parsing,
velocity calculation, and error handling without network access.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from worker.discovery.reddit_poller import RedditPoller


def _make_reddit_response(posts: list[dict] | None = None) -> dict:
    """Build a mock Reddit JSON API response."""
    if posts is None:
        posts = []
    return {
        "data": {
            "children": [{"data": post} for post in posts],
        }
    }


def _make_post(
    title: str = "Test Post",
    permalink: str = "/r/depin/comments/abc123/test_post/",
    selftext: str = "This is test content.",
    ups: int = 100,
    num_comments: int = 25,
    created_utc: float | None = None,
) -> dict:
    """Build a mock Reddit post data dict."""
    if created_utc is None:
        # Default to 2 hours ago
        created_utc = datetime.now(tz=timezone.utc).timestamp() - 7200
    return {
        "title": title,
        "permalink": permalink,
        "selftext": selftext,
        "ups": ups,
        "num_comments": num_comments,
        "created_utc": created_utc,
    }


class TestRedditPollerFetch:
    """Tests for RedditPoller.fetch()."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_extracts_signals_from_subreddit(self) -> None:
        post = _make_post()
        respx.get("https://www.reddit.com/r/depin/hot.json?limit=25").mock(
            return_value=httpx.Response(200, json=_make_reddit_response([post]))
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(subreddits=["depin"], http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 1
        assert signals[0].title == "Test Post"
        assert signals[0].url == "https://www.reddit.com/r/depin/comments/abc123/test_post/"
        assert signals[0].body_preview == "This is test content."
        assert "upvotes" in signals[0].source_metrics
        assert "comments" in signals[0].source_metrics
        assert "velocity" in signals[0].source_metrics

    @pytest.mark.asyncio
    @respx.mock
    async def test_velocity_calculation(self) -> None:
        # Post created exactly 2 hours ago with 100 upvotes => velocity ~50
        two_hours_ago = datetime.now(tz=timezone.utc).timestamp() - 7200
        post = _make_post(ups=100, created_utc=two_hours_ago)
        respx.get("https://www.reddit.com/r/depin/hot.json?limit=25").mock(
            return_value=httpx.Response(200, json=_make_reddit_response([post]))
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(subreddits=["depin"], http_client=client)
            signals = await poller.fetch()

        velocity = signals[0].source_metrics["velocity"]
        # Should be approximately 50 (100 ups / 2 hours)
        assert 45 <= velocity <= 55

    @pytest.mark.asyncio
    @respx.mock
    async def test_multiple_subreddits(self) -> None:
        post1 = _make_post(title="Post 1", permalink="/r/depin/comments/1/p1/")
        post2 = _make_post(title="Post 2", permalink="/r/crypto/comments/2/p2/")

        respx.get("https://www.reddit.com/r/depin/hot.json?limit=25").mock(
            return_value=httpx.Response(200, json=_make_reddit_response([post1]))
        )
        respx.get("https://www.reddit.com/r/cryptocurrency/hot.json?limit=25").mock(
            return_value=httpx.Response(200, json=_make_reddit_response([post2]))
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(
                subreddits=["depin", "cryptocurrency"], http_client=client
            )
            signals = await poller.fetch()

        assert len(signals) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_skips_post_without_title(self) -> None:
        post = _make_post(title="")
        respx.get("https://www.reddit.com/r/depin/hot.json?limit=25").mock(
            return_value=httpx.Response(200, json=_make_reddit_response([post]))
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(subreddits=["depin"], http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_api_error(self) -> None:
        respx.get("https://www.reddit.com/r/depin/hot.json?limit=25").mock(
            return_value=httpx.Response(503)
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(subreddits=["depin"], http_client=client)
            signals = await poller.fetch()

        # Error in one subreddit should not crash; returns empty for that sub
        assert len(signals) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_selftext(self) -> None:
        post = _make_post(selftext="")
        respx.get("https://www.reddit.com/r/depin/hot.json?limit=25").mock(
            return_value=httpx.Response(200, json=_make_reddit_response([post]))
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(subreddits=["depin"], http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 1
        assert signals[0].body_preview is None
