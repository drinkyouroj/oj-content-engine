"""
Reddit RSS feed poller for trend discovery.

Implements PRD Section 2 (Trend Discovery Layer — Reddit source).
Polls Reddit's public RSS feeds for hot posts from configured subreddits
related to DePIN, crypto infrastructure, AI tooling, and self-hosting.

Uses RSS (Atom) feeds instead of the JSON API because Reddit's JSON API
now requires Devvit app registration. RSS feeds are publicly accessible,
provide titles, links, timestamps, and summaries — sufficient for trend
discovery. We lose upvote/comment counts but can still detect signals.

Inputs: Reddit public RSS feeds (no auth required).
Outputs: RawSignal instances with source=REDDIT persisted to the signals table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import ClassVar

import feedparser
import httpx

from worker.app.models.signal import SignalSource
from worker.discovery.base import BasePoller, RawSignal

logger = logging.getLogger(__name__)

#: Default subreddits aligned with drinkYourOJ brand topics
DEFAULT_SUBREDDITS: list[str] = ["depin", "cryptocurrency", "singularity", "selfhosted"]

#: User-Agent header required by Reddit guidelines
REDDIT_USER_AGENT = "oj-content-engine/0.1.0 (trend-discovery-bot)"


class RedditPoller(BasePoller):
    """Poller for Reddit hot posts via public RSS feeds.

    Fetches the top 25 hot posts from each configured subreddit's RSS feed
    and converts them into RawSignal instances. RSS feeds do not include
    upvote or comment counts, so source_metrics contains only what the
    feed provides (author, subreddit).

    Estimated runtime: 2-8s depending on number of subreddits.
    Retry behavior: Handled by ARQ retry settings on the cron job.
    Failure mode: Logs warning per-subreddit and continues.
    """

    source: ClassVar[SignalSource] = SignalSource.REDDIT

    def __init__(
        self,
        subreddits: list[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the Reddit poller.

        Args:
            subreddits: List of subreddit names to poll. Defaults to
                DEFAULT_SUBREDDITS if not provided.
            http_client: Optional httpx.AsyncClient for dependency injection
                in tests. If None, a new client is created per fetch call.
        """
        self._subreddits = subreddits or DEFAULT_SUBREDDITS
        self._http_client = http_client

    async def fetch(self) -> list[RawSignal]:
        """Fetch hot posts from all configured subreddits via RSS.

        Returns:
            List of RawSignal instances from Reddit.
        """
        signals: list[RawSignal] = []

        client = self._http_client or httpx.AsyncClient(
            headers={"User-Agent": REDDIT_USER_AGENT}, timeout=15.0
        )
        manage_client = self._http_client is None

        try:
            for subreddit in self._subreddits:
                try:
                    sub_signals = await self._fetch_subreddit(client, subreddit)
                    signals.extend(sub_signals)
                except Exception:
                    logger.warning(
                        "Failed to fetch subreddit r/%s", subreddit, exc_info=True
                    )
                    continue
        finally:
            if manage_client:
                await client.aclose()

        logger.info(
            "Reddit poller fetched %d signals from %d subreddits",
            len(signals),
            len(self._subreddits),
        )
        return signals

    async def _fetch_subreddit(
        self, client: httpx.AsyncClient, subreddit: str
    ) -> list[RawSignal]:
        """Fetch hot posts from a single subreddit via RSS.

        Args:
            client: httpx async client with proper User-Agent.
            subreddit: Subreddit name (without r/ prefix).

        Returns:
            List of RawSignal instances from this subreddit.

        Raises:
            httpx.HTTPStatusError: If Reddit returns a non-2xx response.
        """
        url = f"https://www.reddit.com/r/{subreddit}/hot.rss"
        response = await client.get(url)
        response.raise_for_status()

        feed = feedparser.parse(response.text)
        signals: list[RawSignal] = []

        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")

            if not title or not link:
                continue

            # Parse published timestamp
            published = entry.get("published", "")
            if published:
                try:
                    created_at = datetime.fromisoformat(published)
                except (ValueError, TypeError):
                    created_at = datetime.now(tz=timezone.utc)
            else:
                created_at = datetime.now(tz=timezone.utc)

            # Extract body preview from summary (HTML content from RSS)
            summary = entry.get("summary", "")
            # Strip HTML tags for a rough plain-text preview
            body_preview = _strip_html(summary)[:500] if summary else None

            author = entry.get("author", "")

            signals.append(
                RawSignal(
                    url=link,
                    title=title,
                    body_preview=body_preview,
                    discovered_at=created_at,
                    source_metrics={
                        "subreddit": subreddit,
                        "author": author,
                    },
                )
            )

        return signals


def _strip_html(html: str) -> str:
    """Remove HTML tags from a string for plain-text preview.

    Simple regex-free approach: walks through the string and drops
    anything between < and >. Good enough for RSS summary snippets.

    Args:
        html: HTML string from the RSS feed summary.

    Returns:
        Plain text with HTML tags removed and whitespace normalized.
    """
    in_tag = False
    chars: list[str] = []
    for ch in html:
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
        elif not in_tag:
            chars.append(ch)
    return " ".join("".join(chars).split())
