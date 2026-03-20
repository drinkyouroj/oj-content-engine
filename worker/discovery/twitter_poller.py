"""
Twitter/X API v2 poller for trend discovery (stub).

Implements PRD Section 2 (Trend Discovery Layer — Twitter/X source).
This is a stub implementation. The full poller requires a paid Twitter API v2
Bearer token. If TWITTER_BEARER_TOKEN is not set, the poller logs an info
message and returns an empty list.

Inputs: TWITTER_BEARER_TOKEN environment variable (optional).
Outputs: RawSignal instances with source=TWITTER persisted to the signals table.
"""

# TODO: Add Nitter RSS fallback (PRD Section 2 - Fallback)

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import ClassVar

import httpx

from worker.app.config import get_settings
from worker.app.models.signal import SignalSource
from worker.discovery.base import BasePoller, RawSignal

logger = logging.getLogger(__name__)

#: Twitter API v2 recent search endpoint
TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

#: Default search query for DePIN and crypto infrastructure topics
DEFAULT_QUERY = "(DePIN OR decentralized infrastructure OR blockchain infrastructure) -is:retweet lang:en"


class TwitterPoller(BasePoller):
    """Poller for Twitter/X via the API v2 recent search endpoint.

    This is a stub implementation. When no bearer token is configured,
    the poller returns an empty list without making any API calls.

    Estimated runtime: 1-3s when token is configured, instant otherwise.
    Retry behavior: Handled by ARQ retry settings on the cron job.
    Failure mode: Returns empty list and logs error on API failure.
    """

    source: ClassVar[SignalSource] = SignalSource.TWITTER

    def __init__(
        self,
        bearer_token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the Twitter poller.

        Args:
            bearer_token: Twitter API v2 Bearer token. If None, reads from
                the TWITTER_BEARER_TOKEN env var.
            http_client: Optional httpx.AsyncClient for dependency injection
                in tests. If None, a new client is created per fetch call.
        """
        if bearer_token is not None:
            self._bearer_token = bearer_token
        else:
            self._bearer_token = get_settings().twitter_bearer_token
        self._http_client = http_client

    async def fetch(self) -> list[RawSignal]:
        """Fetch recent tweets matching DePIN/crypto infrastructure topics.

        If no bearer token is configured, logs an info message and returns
        an empty list immediately.

        Returns:
            List of RawSignal instances from Twitter, or empty list if
            the poller is disabled.
        """
        if not self._bearer_token:
            logger.info("Twitter poller disabled — no bearer token configured")
            return []

        client = self._http_client or httpx.AsyncClient(timeout=15.0)
        manage_client = self._http_client is None

        try:
            response = await client.get(
                TWITTER_SEARCH_URL,
                params={
                    "query": DEFAULT_QUERY,
                    "max_results": 25,
                    "tweet.fields": "created_at,public_metrics,text",
                },
                headers={"Authorization": f"Bearer {self._bearer_token}"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.error("Failed to fetch Twitter API", exc_info=True)
            return []
        finally:
            if manage_client:
                await client.aclose()

        tweets = data.get("data", [])
        signals: list[RawSignal] = []

        for tweet in tweets:
            tweet_id = tweet.get("id", "")
            text = tweet.get("text", "")
            created_at_str = tweet.get("created_at", "")
            metrics = tweet.get("public_metrics", {})

            if not text or not tweet_id:
                continue

            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created_at = datetime.now(tz=timezone.utc)

            signals.append(
                RawSignal(
                    url=f"https://twitter.com/i/web/status/{tweet_id}",
                    title=text[:140],
                    body_preview=text[:500],
                    discovered_at=created_at,
                    source_metrics={
                        "retweets": metrics.get("retweet_count", 0),
                        "likes": metrics.get("like_count", 0),
                        "replies": metrics.get("reply_count", 0),
                    },
                )
            )

        logger.info("Twitter poller fetched %d signals", len(signals))
        return signals
