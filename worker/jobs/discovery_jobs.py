"""
ARQ job definitions for trend discovery pollers.

Wraps each poller in an ARQ-compatible async function that obtains
a database session and invokes the poller's run() method. Registered
in WorkerSettings.functions and WorkerSettings.cron_jobs.

Implements PRD Section 2 (Trend Discovery Layer — scheduled polling).
"""

from __future__ import annotations

import logging

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory

logger = logging.getLogger(__name__)


async def _get_session():
    """Create a one-shot async database session for a job.

    Returns:
        AsyncSession bound to the configured DATABASE_URL.
    """
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    session = session_factory()
    return session, engine


async def poll_rss(ctx: dict) -> int:
    """ARQ job: run the RSS poller.

    Polls all configured RSS feeds and persists new signals.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Number of new signals inserted.

    Estimated runtime: 5-30s depending on number of feeds.
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Logs error; does not block other pollers.
    """
    from worker.discovery.rss_poller import RSSPoller

    session, engine = await _get_session()
    try:
        poller = RSSPoller()
        count = await poller.run(session)
        logger.info("poll_rss completed: %d new signals", count)
        return count
    finally:
        await session.close()
        await engine.dispose()


async def poll_reddit(ctx: dict) -> int:
    """ARQ job: run the Reddit poller.

    Polls configured subreddits for hot posts and persists new signals.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Number of new signals inserted.

    Estimated runtime: 5-15s depending on number of subreddits.
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Logs error; does not block other pollers.
    """
    from worker.discovery.reddit_poller import RedditPoller

    session, engine = await _get_session()
    try:
        poller = RedditPoller()
        count = await poller.run(session)
        logger.info("poll_reddit completed: %d new signals", count)
        return count
    finally:
        await session.close()
        await engine.dispose()


async def poll_hn(ctx: dict) -> int:
    """ARQ job: run the Hacker News poller.

    Polls the HN Algolia API for recent stories and persists new signals.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Number of new signals inserted.

    Estimated runtime: 2-5s.
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Logs error; does not block other pollers.
    """
    from worker.discovery.hn_poller import HNPoller

    session, engine = await _get_session()
    try:
        poller = HNPoller()
        count = await poller.run(session)
        logger.info("poll_hn completed: %d new signals", count)
        return count
    finally:
        await session.close()
        await engine.dispose()


async def poll_twitter(ctx: dict) -> int:
    """ARQ job: run the Twitter/X poller.

    Polls the Twitter API v2 for recent tweets matching DePIN/crypto topics.
    If no bearer token is configured, returns 0 immediately.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Number of new signals inserted.

    Estimated runtime: 1-5s when token is set, instant otherwise.
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Returns 0 if disabled; logs error on API failure.
    """
    from worker.discovery.twitter_poller import TwitterPoller

    session, engine = await _get_session()
    try:
        poller = TwitterPoller()
        count = await poller.run(session)
        logger.info("poll_twitter completed: %d new signals", count)
        return count
    finally:
        await session.close()
        await engine.dispose()
