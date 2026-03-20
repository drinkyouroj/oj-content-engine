"""
Unit tests for the Hacker News poller.

Uses respx to mock httpx responses and test Algolia API response parsing,
velocity calculation, and error handling without network access.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from worker.discovery.hn_poller import HN_ALGOLIA_URL, HNPoller


def _make_hn_response(hits: list[dict] | None = None) -> dict:
    """Build a mock HN Algolia API response."""
    return {"hits": hits or []}


def _make_hit(
    title: str = "Show HN: Test Project",
    url: str = "https://example.com/project",
    object_id: str = "12345",
    story_text: str = "This is a test story.",
    points: int = 150,
    num_comments: int = 42,
    created_at: str | None = None,
) -> dict:
    """Build a mock HN Algolia hit."""
    if created_at is None:
        # Default to 3 hours ago
        dt = datetime.now(tz=timezone.utc).replace(microsecond=0)
        from datetime import timedelta
        dt = dt - timedelta(hours=3)
        created_at = dt.isoformat().replace("+00:00", "Z")
    return {
        "title": title,
        "url": url,
        "objectID": object_id,
        "story_text": story_text,
        "points": points,
        "num_comments": num_comments,
        "created_at": created_at,
    }


class TestHNPollerFetch:
    """Tests for HNPoller.fetch()."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_extracts_signals(self) -> None:
        hit = _make_hit()
        respx.get(HN_ALGOLIA_URL).mock(
            return_value=httpx.Response(200, json=_make_hn_response([hit]))
        )

        async with httpx.AsyncClient() as client:
            poller = HNPoller(http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 1
        assert signals[0].title == "Show HN: Test Project"
        assert signals[0].url == "https://example.com/project"
        assert signals[0].body_preview == "This is a test story."
        assert "points" in signals[0].source_metrics
        assert "comments" in signals[0].source_metrics
        assert "velocity" in signals[0].source_metrics

    @pytest.mark.asyncio
    @respx.mock
    async def test_velocity_calculation(self) -> None:
        from datetime import timedelta

        three_hours_ago = datetime.now(tz=timezone.utc).replace(microsecond=0) - timedelta(hours=3)
        hit = _make_hit(
            points=300,
            created_at=three_hours_ago.isoformat().replace("+00:00", "Z"),
        )
        respx.get(HN_ALGOLIA_URL).mock(
            return_value=httpx.Response(200, json=_make_hn_response([hit]))
        )

        async with httpx.AsyncClient() as client:
            poller = HNPoller(http_client=client)
            signals = await poller.fetch()

        velocity = signals[0].source_metrics["velocity"]
        # 300 points / 3 hours = ~100
        assert 90 <= velocity <= 110

    @pytest.mark.asyncio
    @respx.mock
    async def test_falls_back_to_hn_url_when_no_external_url(self) -> None:
        hit = _make_hit(url=None, object_id="99999")
        # url key present but None — simulates HN self-posts
        hit["url"] = None
        respx.get(HN_ALGOLIA_URL).mock(
            return_value=httpx.Response(200, json=_make_hn_response([hit]))
        )

        async with httpx.AsyncClient() as client:
            poller = HNPoller(http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 1
        assert signals[0].url == "https://news.ycombinator.com/item?id=99999"

    @pytest.mark.asyncio
    @respx.mock
    async def test_skips_hit_without_title(self) -> None:
        hit = _make_hit(title="")
        respx.get(HN_ALGOLIA_URL).mock(
            return_value=httpx.Response(200, json=_make_hn_response([hit]))
        )

        async with httpx.AsyncClient() as client:
            poller = HNPoller(http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_api_error(self) -> None:
        respx.get(HN_ALGOLIA_URL).mock(return_value=httpx.Response(500))

        async with httpx.AsyncClient() as client:
            poller = HNPoller(http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_empty_story_text(self) -> None:
        hit = _make_hit(story_text="")
        respx.get(HN_ALGOLIA_URL).mock(
            return_value=httpx.Response(200, json=_make_hn_response([hit]))
        )

        async with httpx.AsyncClient() as client:
            poller = HNPoller(http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 1
        assert signals[0].body_preview is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_multiple_hits(self) -> None:
        hits = [
            _make_hit(title=f"Story {i}", object_id=str(i))
            for i in range(5)
        ]
        respx.get(HN_ALGOLIA_URL).mock(
            return_value=httpx.Response(200, json=_make_hn_response(hits))
        )

        async with httpx.AsyncClient() as client:
            poller = HNPoller(http_client=client)
            signals = await poller.fetch()

        assert len(signals) == 5
