"""
ARQ job definitions for trend discovery pollers.

Wraps each poller in an ARQ-compatible async function that obtains
a database session and invokes the poller's run() method. Registered
in WorkerSettings.functions and WorkerSettings.cron_jobs.

Implements PRD Section 2 (Trend Discovery Layer — scheduled polling).
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory

logger = logging.getLogger(__name__)


async def _get_session() -> tuple[AsyncSession, AsyncEngine]:
    """Create a one-shot async database session for a job.

    Returns:
        Tuple of (AsyncSession, AsyncEngine) bound to the configured DATABASE_URL.
        Caller is responsible for closing session and disposing engine.
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

    t0 = time.monotonic()
    logger.info("Starting RSS poll", extra={"event": "job_start", "stage": "discovery", "source": "rss"})

    session, engine = await _get_session()
    try:
        poller = RSSPoller()
        count = await poller.run(session)
        elapsed = round(time.monotonic() - t0, 2)
        logger.info(
            "RSS poll complete: %d new signals in %.2fs",
            count, elapsed,
            extra={"event": "job_complete", "stage": "discovery", "source": "rss", "signals": count, "elapsed_s": elapsed},
        )
        return count
    except Exception:
        elapsed = round(time.monotonic() - t0, 2)
        logger.exception(
            "RSS poll failed after %.2fs", elapsed,
            extra={"event": "job_error", "stage": "discovery", "source": "rss", "elapsed_s": elapsed},
        )
        raise
    finally:
        await session.close()
        await engine.dispose()


async def poll_reddit(ctx: dict) -> int:
    """ARQ job: run the Reddit poller.

    Polls configured subreddits for hot posts via RSS and persists new signals.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Number of new signals inserted.

    Estimated runtime: 5-15s depending on number of subreddits.
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Logs error; does not block other pollers.
    """
    from worker.discovery.reddit_poller import RedditPoller

    t0 = time.monotonic()
    logger.info("Starting Reddit poll", extra={"event": "job_start", "stage": "discovery", "source": "reddit"})

    session, engine = await _get_session()
    try:
        poller = RedditPoller()
        count = await poller.run(session)
        elapsed = round(time.monotonic() - t0, 2)
        logger.info(
            "Reddit poll complete: %d new signals in %.2fs",
            count, elapsed,
            extra={"event": "job_complete", "stage": "discovery", "source": "reddit", "signals": count, "elapsed_s": elapsed},
        )
        return count
    except Exception:
        elapsed = round(time.monotonic() - t0, 2)
        logger.exception(
            "Reddit poll failed after %.2fs", elapsed,
            extra={"event": "job_error", "stage": "discovery", "source": "reddit", "elapsed_s": elapsed},
        )
        raise
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

    t0 = time.monotonic()
    logger.info("Starting HN poll", extra={"event": "job_start", "stage": "discovery", "source": "hn"})

    session, engine = await _get_session()
    try:
        poller = HNPoller()
        count = await poller.run(session)
        elapsed = round(time.monotonic() - t0, 2)
        logger.info(
            "HN poll complete: %d new signals in %.2fs",
            count, elapsed,
            extra={"event": "job_complete", "stage": "discovery", "source": "hn", "signals": count, "elapsed_s": elapsed},
        )
        return count
    except Exception:
        elapsed = round(time.monotonic() - t0, 2)
        logger.exception(
            "HN poll failed after %.2fs", elapsed,
            extra={"event": "job_error", "stage": "discovery", "source": "hn", "elapsed_s": elapsed},
        )
        raise
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

    t0 = time.monotonic()
    logger.info("Starting Twitter poll", extra={"event": "job_start", "stage": "discovery", "source": "twitter"})

    session, engine = await _get_session()
    try:
        poller = TwitterPoller()
        count = await poller.run(session)
        elapsed = round(time.monotonic() - t0, 2)
        logger.info(
            "Twitter poll complete: %d new signals in %.2fs",
            count, elapsed,
            extra={"event": "job_complete", "stage": "discovery", "source": "twitter", "signals": count, "elapsed_s": elapsed},
        )
        return count
    except Exception:
        elapsed = round(time.monotonic() - t0, 2)
        logger.exception(
            "Twitter poll failed after %.2fs", elapsed,
            extra={"event": "job_error", "stage": "discovery", "source": "twitter", "elapsed_s": elapsed},
        )
        raise
    finally:
        await session.close()
        await engine.dispose()
