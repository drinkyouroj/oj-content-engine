"""
Unit tests for the RSS poller.

Mocks feedparser responses to test signal extraction, date parsing,
and error handling without network access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from worker.discovery.rss_poller import RSSPoller


def _make_entry(
    title: str = "Test Article",
    link: str = "https://example.com/article",
    summary: str = "This is a test summary.",
    published_parsed: tuple | None = (2025, 1, 15, 12, 0, 0, 2, 15, 0),
) -> MagicMock:
    """Create a mock feedparser entry."""
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.summary = summary
    entry.description = summary
    entry.published_parsed = published_parsed
    entry.published = "Wed, 15 Jan 2025 12:00:00 GMT"
    return entry


def _make_feed(entries: list | None = None, bozo: bool = False) -> MagicMock:
    """Create a mock feedparser.parse() result."""
    feed = MagicMock()
    feed.entries = entries or []
    feed.bozo = bozo
    feed.bozo_exception = Exception("parse error") if bozo else None
    return feed


class TestRSSPollerFetch:
    """Tests for RSSPoller.fetch()."""

    @pytest.mark.asyncio
    @patch("worker.discovery.rss_poller.feedparser.parse")
    async def test_extracts_signals_from_feed(self, mock_parse: MagicMock) -> None:
        entry = _make_entry()
        mock_parse.return_value = _make_feed(entries=[entry])

        poller = RSSPoller(feed_urls=["https://example.com/feed.xml"])
        signals = await poller.fetch()

        assert len(signals) == 1
        assert signals[0].url == "https://example.com/article"
        assert signals[0].title == "Test Article"
        assert signals[0].body_preview == "This is a test summary."
        assert signals[0].source_metrics == {}

    @pytest.mark.asyncio
    @patch("worker.discovery.rss_poller.feedparser.parse")
    async def test_skips_entries_without_link(self, mock_parse: MagicMock) -> None:
        entry = _make_entry(link=None)
        mock_parse.return_value = _make_feed(entries=[entry])

        poller = RSSPoller(feed_urls=["https://example.com/feed.xml"])
        signals = await poller.fetch()

        assert len(signals) == 0

    @pytest.mark.asyncio
    @patch("worker.discovery.rss_poller.feedparser.parse")
    async def test_skips_entries_without_title(self, mock_parse: MagicMock) -> None:
        entry = _make_entry(title=None)
        mock_parse.return_value = _make_feed(entries=[entry])

        poller = RSSPoller(feed_urls=["https://example.com/feed.xml"])
        signals = await poller.fetch()

        assert len(signals) == 0

    @pytest.mark.asyncio
    @patch("worker.discovery.rss_poller.feedparser.parse")
    async def test_handles_bozo_feed_with_no_entries(self, mock_parse: MagicMock) -> None:
        mock_parse.return_value = _make_feed(entries=[], bozo=True)

        poller = RSSPoller(feed_urls=["https://example.com/bad-feed.xml"])
        signals = await poller.fetch()

        assert len(signals) == 0

    @pytest.mark.asyncio
    @patch("worker.discovery.rss_poller.feedparser.parse")
    async def test_handles_bozo_feed_with_entries(self, mock_parse: MagicMock) -> None:
        """A bozo feed that still has entries should process them."""
        entry = _make_entry()
        feed = _make_feed(entries=[entry], bozo=True)
        mock_parse.return_value = feed

        poller = RSSPoller(feed_urls=["https://example.com/feed.xml"])
        signals = await poller.fetch()

        assert len(signals) == 1

    @pytest.mark.asyncio
    @patch("worker.discovery.rss_poller.feedparser.parse")
    async def test_multiple_feeds(self, mock_parse: MagicMock) -> None:
        entry1 = _make_entry(title="Article 1", link="https://a.com/1")
        entry2 = _make_entry(title="Article 2", link="https://b.com/2")
        mock_parse.side_effect = [
            _make_feed(entries=[entry1]),
            _make_feed(entries=[entry2]),
        ]

        poller = RSSPoller(feed_urls=["https://a.com/feed", "https://b.com/feed"])
        signals = await poller.fetch()

        assert len(signals) == 2

    @pytest.mark.asyncio
    @patch("worker.discovery.rss_poller.feedparser.parse")
    async def test_fallback_date_when_no_published(self, mock_parse: MagicMock) -> None:
        entry = _make_entry(published_parsed=None)
        entry.published = None
        mock_parse.return_value = _make_feed(entries=[entry])

        poller = RSSPoller(feed_urls=["https://example.com/feed.xml"])
        signals = await poller.fetch()

        assert len(signals) == 1
        # Should fallback to approximately now
        assert (datetime.now(tz=timezone.utc) - signals[0].discovered_at).total_seconds() < 5

    @pytest.mark.asyncio
    @patch("worker.discovery.rss_poller.feedparser.parse")
    async def test_truncates_body_preview(self, mock_parse: MagicMock) -> None:
        long_summary = "x" * 1000
        entry = _make_entry(summary=long_summary)
        mock_parse.return_value = _make_feed(entries=[entry])

        poller = RSSPoller(feed_urls=["https://example.com/feed.xml"])
        signals = await poller.fetch()

        assert len(signals[0].body_preview) == 500

    @pytest.mark.asyncio
    @patch("worker.discovery.rss_poller.feedparser.parse")
    async def test_parse_exception_continues(self, mock_parse: MagicMock) -> None:
        """If feedparser.parse raises, the poller should continue."""
        mock_parse.side_effect = Exception("network error")

        poller = RSSPoller(feed_urls=["https://example.com/feed.xml"])
        signals = await poller.fetch()

        assert len(signals) == 0
