"""
Research module for steered topic discovery.

Searches existing signals in Postgres and supplements with Brave Search API
results. Used by the /api/research endpoint for on-demand topic research.
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.signal import Signal

logger = logging.getLogger(__name__)


async def search_existing_signals(
    query: str,
    session: AsyncSession,
    limit: int = 10,
) -> list[dict]:
    """Search existing signals by title and body_preview using ILIKE.

    Args:
        query: Search query string to match against signal titles and previews.
        session: Async SQLAlchemy session for database access.
        limit: Maximum number of results to return.

    Returns:
        List of dicts with title, url, body_preview, source, and published_at.
    """
    escaped = query.replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    stmt = (
        select(Signal.title, Signal.url, Signal.body_preview, Signal.source, Signal.discovered_at)
        .where(or_(Signal.title.ilike(pattern), Signal.body_preview.ilike(pattern)))
        .order_by(Signal.discovered_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.mappings().all()

    return [
        {
            "title": row["title"],
            "url": row["url"],
            "body_preview": (row["body_preview"] or "")[:200],
            "source": row["source"].value if hasattr(row["source"], "value") else str(row["source"]),
            "published_at": row["discovered_at"].isoformat() if row["discovered_at"] else None,
        }
        for row in rows
    ]


async def search_web(
    query: str,
    api_key: str,
    limit: int = 10,
) -> list[dict]:
    """Search the web via Brave Search API. Returns empty list on failure.

    Args:
        query: Search query string.
        api_key: Brave Search API subscription token.
        limit: Maximum number of results to return.

    Returns:
        List of dicts with title, url, body_preview, source, and published_at.
    """
    if not api_key:
        logger.warning("Brave Search API key not configured, skipping web search")
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": limit, "freshness": "pw"},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("web", {}).get("results", [])[:limit]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "body_preview": (item.get("description", ""))[:200],
                "source": "web",
                "published_at": item.get("page_age") or item.get("age"),
            })
        return results

    except Exception:
        logger.exception("Brave Search API call failed for query: %s", query)
        return []


def merge_and_deduplicate(
    db_results: list[dict],
    web_results: list[dict],
    max_results: int = 15,
) -> list[dict]:
    """Merge DB and web results, deduplicate by URL, prefer DB results.

    Args:
        db_results: Results from the local signal database.
        web_results: Results from Brave Search API.
        max_results: Maximum number of merged results to return.

    Returns:
        Deduplicated list of result dicts, DB results first.
    """
    seen_urls: set[str] = set()
    merged: list[dict] = []

    for result in db_results + web_results:
        url = result.get("url", "").rstrip("/").lower()
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(result)
        if len(merged) >= max_results:
            break

    return merged
