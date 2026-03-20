"""Tests for the steered topic research module."""
from datetime import datetime, timezone

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock
from worker.discovery.research import search_existing_signals, search_web, merge_and_deduplicate


@pytest.mark.asyncio
async def test_search_existing_signals_returns_matching_results():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "title": "Seahawks draft strategy",
            "url": "https://example.com/seahawks",
            "body_preview": "NFL offseason analysis",
            "source": "rss",
            "discovered_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
        }
    ]
    mock_session.execute.return_value = mock_result
    results = await search_existing_signals("Seahawks", mock_session, limit=10)
    assert len(results) == 1
    assert results[0]["title"] == "Seahawks draft strategy"


@pytest.mark.asyncio
async def test_search_web_returns_results(respx_mock):
    respx_mock.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "NFL Draft Analysis",
                            "url": "https://example.com/nfl",
                            "description": "Draft picks breakdown",
                        },
                    ]
                }
            },
        )
    )
    results = await search_web("NFL draft", "fake-key", limit=5)
    assert len(results) == 1
    assert results[0]["source"] == "web"


@pytest.mark.asyncio
async def test_search_web_returns_empty_on_failure(respx_mock):
    respx_mock.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(500)
    )
    results = await search_web("test", "fake-key")
    assert results == []


def test_merge_and_deduplicate_removes_duplicate_urls():
    db_results = [
        {
            "title": "A",
            "url": "https://example.com/a",
            "body_preview": "...",
            "source": "rss",
            "published_at": None,
        }
    ]
    web_results = [
        {
            "title": "A (web)",
            "url": "https://example.com/a",
            "body_preview": "...",
            "source": "web",
            "published_at": None,
        },
        {
            "title": "B",
            "url": "https://example.com/b",
            "body_preview": "...",
            "source": "web",
            "published_at": None,
        },
    ]
    merged = merge_and_deduplicate(db_results, web_results, max_results=15)
    assert len(merged) == 2
    assert merged[0]["title"] == "A"
    assert merged[1]["title"] == "B"
