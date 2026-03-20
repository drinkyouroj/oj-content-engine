"""
RSS/Atom feed poller for trend discovery.

Implements PRD Section 2 (Trend Discovery Layer — RSS source).
Reads a comma-separated list of feed URLs from the RSS_FEED_URLS env var,
parses each with feedparser, and returns RawSignal instances for new entries.

Inputs: RSS_FEED_URLS environment variable (comma-separated).
Outputs: RawSignal instances with source=RSS persisted to the signals table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import ClassVar

import feedparser
from email.utils import parsedate_to_datetime

from worker.app.config import get_settings
from worker.app.models.signal import SignalSource
from worker.discovery.base import BasePoller, RawSignal

logger = logging.getLogger(__name__)


class RSSPoller(BasePoller):
    """Poller for RSS/Atom feeds.

    Parses feeds using the feedparser library. Handles malformed feeds
    and missing fields gracefully — logs a warning and skips entries
    that cannot be parsed.

    Estimated runtime: 1-5s per feed depending on feed size and latency.
    Retry behavior: Handled by ARQ retry settings on the cron job.
    Failure mode: Logs warning per-feed and continues; never crashes the batch.
    """

    source: ClassVar[SignalSource] = SignalSource.RSS

    def __init__(self, feed_urls: list[str] | None = None) -> None:
        """Initialize the RSS poller.

        Args:
            feed_urls: List of RSS feed URLs to poll. If None, reads from
                the RSS_FEED_URLS env var (comma-separated).
        """
        if feed_urls is not None:
            self._feed_urls = feed_urls
        else:
            raw = get_settings().rss_feed_urls
            self._feed_urls = [u.strip() for u in raw.split(",") if u.strip()]

    async def fetch(self) -> list[RawSignal]:
        """Fetch and parse all configured RSS feeds.

        Returns:
            List of RawSignal instances extracted from feed entries.
        """
        signals: list[RawSignal] = []

        for url in self._feed_urls:
            try:
                feed = feedparser.parse(url)
                if feed.bozo and not feed.entries:
                    logger.warning("Failed to parse feed %s: %s", url, feed.bozo_exception)
                    continue

                for entry in feed.entries:
                    raw = self._parse_entry(entry, url)
                    if raw is not None:
                        signals.append(raw)
            except Exception:
                logger.warning("Unexpected error parsing feed %s", url, exc_info=True)
                continue

        logger.info("RSS poller fetched %d signals from %d feeds", len(signals), len(self._feed_urls))
        return signals

    def _parse_entry(self, entry: feedparser.FeedParserDict, feed_url: str) -> RawSignal | None:
        """Parse a single feed entry into a RawSignal.

        Args:
            entry: A feedparser entry dict.
            feed_url: The source feed URL (for logging).

        Returns:
            RawSignal if the entry has required fields, None otherwise.
        """
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)

        if not link or not title:
            logger.debug("Skipping entry without link or title in feed %s", feed_url)
            return None

        # Extract body preview from summary or description
        body_preview = getattr(entry, "summary", None) or getattr(entry, "description", None)
        if body_preview:
            body_preview = body_preview[:500]

        # Parse published date
        discovered_at = self._parse_date(entry)

        return RawSignal(
            url=link,
            title=title,
            body_preview=body_preview,
            discovered_at=discovered_at,
            source_metrics={},
        )

    @staticmethod
    def _parse_date(entry: feedparser.FeedParserDict) -> datetime:
        """Extract and parse the publication date from a feed entry.

        Falls back to current UTC time if no date is available or parseable.

        Args:
            entry: A feedparser entry dict.

        Returns:
            Timezone-aware datetime of the entry's publication.
        """
        # feedparser provides published_parsed as a time.struct_time
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                from calendar import timegm
                ts = timegm(entry.published_parsed)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, OverflowError, TypeError):
                pass

        # Try the raw published string
        published = getattr(entry, "published", None)
        if published:
            try:
                return parsedate_to_datetime(published).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        # Fallback to now
        return datetime.now(tz=timezone.utc)
