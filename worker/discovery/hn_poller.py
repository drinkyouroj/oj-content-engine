"""
Hacker News Algolia API poller for trend discovery.

Implements PRD Section 2 (Trend Discovery Layer — HN source).
Polls the HN Algolia search API for recent stories, extracting
engagement metrics and computing a velocity score.

Inputs: HN Algolia API (public, no auth required).
Outputs: RawSignal instances with source=HN persisted to the signals table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import ClassVar

import httpx

from worker.app.models.signal import SignalSource
from worker.discovery.base import BasePoller, RawSignal

logger = logging.getLogger(__name__)

#: HN Algolia API endpoint for story search
HN_ALGOLIA_URL = "http://hn.algolia.com/api/v1/search"


class HNPoller(BasePoller):
    """Poller for Hacker News stories via the Algolia search API.

    Fetches the 30 most recent stories and computes a velocity metric
    (points per hour since creation).

    Estimated runtime: 1-3s per request.
    Retry behavior: Handled by ARQ retry settings on the cron job.
    Failure mode: Logs error and returns empty list.
    """

    source: ClassVar[SignalSource] = SignalSource.HN

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """Initialize the HN poller.

        Args:
            http_client: Optional httpx.AsyncClient for dependency injection
                in tests. If None, a new client is created per fetch call.
        """
        self._http_client = http_client

    async def fetch(self) -> list[RawSignal]:
        """Fetch recent stories from the HN Algolia API.

        Returns:
            List of RawSignal instances from Hacker News.
        """
        client = self._http_client or httpx.AsyncClient(timeout=15.0)
        manage_client = self._http_client is None

        try:
            response = await client.get(
                HN_ALGOLIA_URL, params={"tags": "story", "hitsPerPage": 30}
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.error("Failed to fetch HN Algolia API", exc_info=True)
            return []
        finally:
            if manage_client:
                await client.aclose()

        hits = data.get("hits", [])
        signals: list[RawSignal] = []
        now = datetime.now(tz=timezone.utc)

        for hit in hits:
            title = hit.get("title", "")
            if not title:
                continue

            # Prefer the external URL; fall back to HN item page
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            story_text = hit.get("story_text") or ""
            points = hit.get("points", 0) or 0
            num_comments = hit.get("num_comments", 0) or 0

            # Parse created_at from the ISO timestamp
            created_at_str = hit.get("created_at", "")
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created_at = now

            # Compute velocity: points per hour since creation
            hours_since_created = max(
                (now - created_at).total_seconds() / 3600.0, 0.1
            )
            velocity = round(points / hours_since_created, 2)

            signals.append(
                RawSignal(
                    url=url,
                    title=title,
                    body_preview=story_text[:500] if story_text else None,
                    discovered_at=created_at,
                    source_metrics={
                        "points": points,
                        "comments": num_comments,
                        "velocity": velocity,
                    },
                )
            )

        logger.info("HN poller fetched %d signals", len(signals))
        return signals
