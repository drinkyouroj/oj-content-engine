"""
Reddit JSON API poller for trend discovery.

Implements PRD Section 2 (Trend Discovery Layer — Reddit source).
Polls the public Reddit JSON API for hot posts from configured subreddits
related to DePIN, crypto infrastructure, AI tooling, and self-hosting.

Inputs: Public Reddit JSON API (no auth required for read-only).
Outputs: RawSignal instances with source=REDDIT persisted to the signals table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import ClassVar

import httpx

from worker.app.models.signal import SignalSource
from worker.discovery.base import BasePoller, RawSignal

logger = logging.getLogger(__name__)

#: Default subreddits aligned with drinkYourOJ brand topics
DEFAULT_SUBREDDITS: list[str] = ["depin", "cryptocurrency", "singularity", "selfhosted"]

#: User-Agent header required by Reddit API guidelines
REDDIT_USER_AGENT = "oj-content-engine/0.1.0 (trend-discovery-bot)"


class RedditPoller(BasePoller):
    """Poller for Reddit hot posts via the public JSON API.

    Fetches the top 25 hot posts from each configured subreddit and
    computes a velocity metric (upvotes per hour since creation).

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
        """Fetch hot posts from all configured subreddits.

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
        """Fetch hot posts from a single subreddit.

        Args:
            client: httpx async client with proper User-Agent.
            subreddit: Subreddit name (without r/ prefix).

        Returns:
            List of RawSignal instances from this subreddit.

        Raises:
            httpx.HTTPStatusError: If the Reddit API returns a non-2xx response.
        """
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
        response = await client.get(url)
        response.raise_for_status()

        data = response.json()
        children = data.get("data", {}).get("children", [])

        signals: list[RawSignal] = []
        now = datetime.now(tz=timezone.utc)

        for child in children:
            post = child.get("data", {})
            if not post:
                continue

            title = post.get("title", "")
            permalink = post.get("permalink", "")
            selftext = post.get("selftext", "")
            ups = post.get("ups", 0)
            num_comments = post.get("num_comments", 0)
            created_utc = post.get("created_utc", 0)

            if not title or not permalink:
                continue

            post_url = f"https://www.reddit.com{permalink}"
            created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)

            # Compute velocity: upvotes per hour since creation
            hours_since_created = max(
                (now - created_at).total_seconds() / 3600.0, 0.1
            )
            velocity = round(ups / hours_since_created, 2)

            signals.append(
                RawSignal(
                    url=post_url,
                    title=title,
                    body_preview=selftext[:500] if selftext else None,
                    discovered_at=created_at,
                    source_metrics={
                        "upvotes": ups,
                        "comments": num_comments,
                        "velocity": velocity,
                    },
                )
            )

        return signals
