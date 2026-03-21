"""
Unit tests for the Reddit RSS poller.

Uses respx to mock httpx responses with RSS/Atom XML and test feed parsing,
signal extraction, and error handling without network access.
"""

from __future__ import annotations


import httpx
import pytest
import respx

from worker.discovery.reddit_poller import RedditPoller


def _make_rss_feed(entries: list[dict] | None = None, subreddit: str = "depin") -> str:
    """Build a mock Reddit RSS (Atom) feed XML string."""
    if entries is None:
        entries = []
    items = ""
    for entry in entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        published = entry.get("published", "2025-01-01T12:00:00+00:00")
        summary = entry.get("summary", "")
        author = entry.get("author", "testuser")
        items += f"""
        <entry>
            <title>{title}</title>
            <link href="{link}" />
            <published>{published}</published>
            <summary type="html">{summary}</summary>
            <author><name>{author}</name></author>
        </entry>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>r/{subreddit} hot posts</title>
    {items}
</feed>"""


def _make_entry(
    title: str = "Test Post",
    link: str = "https://www.reddit.com/r/depin/comments/abc123/test_post/",
    summary: str = "<p>This is test content.</p>",
    author: str = "testuser",
    published: str = "2025-01-01T12:00:00+00:00",
) -> dict:
    """Build a mock RSS entry dict for constructing feeds."""
    return {
        "title": title,
        "link": link,
        "summary": summary,
        "author": author,
        "published": published,
    }


class TestRedditPollerFetch:
    """Tests for RedditPoller.fetch()."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_extracts_signals_from_subreddit(self) -> None:
        entry = _make_entry()
        rss_xml = _make_rss_feed([entry])
        respx.get("https://www.reddit.com/r/depin/hot.rss").mock(
            return_value=httpx.Response(200, text=rss_xml)
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(subreddits=["depin"], http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 1
        assert signals[0].title == "Test Post"
        assert signals[0].url == "https://www.reddit.com/r/depin/comments/abc123/test_post/"
        assert signals[0].body_preview == "This is test content."
        assert signals[0].source_metrics["subreddit"] == "depin"
        assert signals[0].source_metrics["author"] == "testuser"

    @pytest.mark.asyncio
    @respx.mock
    async def test_multiple_subreddits(self) -> None:
        entry1 = _make_entry(title="Post 1", link="https://www.reddit.com/r/depin/comments/1/p1/")
        entry2 = _make_entry(title="Post 2", link="https://www.reddit.com/r/crypto/comments/2/p2/")

        respx.get("https://www.reddit.com/r/depin/hot.rss").mock(
            return_value=httpx.Response(200, text=_make_rss_feed([entry1], subreddit="depin"))
        )
        respx.get("https://www.reddit.com/r/cryptocurrency/hot.rss").mock(
            return_value=httpx.Response(200, text=_make_rss_feed([entry2], subreddit="cryptocurrency"))
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
        entry = _make_entry(title="")
        rss_xml = _make_rss_feed([entry])
        respx.get("https://www.reddit.com/r/depin/hot.rss").mock(
            return_value=httpx.Response(200, text=rss_xml)
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(subreddits=["depin"], http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_api_error(self) -> None:
        respx.get("https://www.reddit.com/r/depin/hot.rss").mock(
            return_value=httpx.Response(503)
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(subreddits=["depin"], http_client=client)
            signals = await poller.fetch()

        # Error in one subreddit should not crash; returns empty for that sub
        assert len(signals) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_summary(self) -> None:
        entry = _make_entry(summary="")
        rss_xml = _make_rss_feed([entry])
        respx.get("https://www.reddit.com/r/depin/hot.rss").mock(
            return_value=httpx.Response(200, text=rss_xml)
        )

        async with httpx.AsyncClient() as client:
            poller = RedditPoller(subreddits=["depin"], http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 1
        assert signals[0].body_preview is None
