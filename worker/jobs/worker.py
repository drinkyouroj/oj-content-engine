"""
ARQ worker configuration and job registry.

Connects to Upstash Redis via ARQ_REDIS_URL. Registers discovery pollers
as cron jobs for automated trend ingestion.

Implements PRD Section 8 (ARQ as async task queue).
"""

from __future__ import annotations

import logging

from arq.connections import RedisSettings
from arq.cron import cron

from worker.jobs.discovery_jobs import poll_hn, poll_reddit, poll_rss, poll_twitter

logger = logging.getLogger(__name__)


def _build_redis_settings() -> RedisSettings:
    """Build Redis connection settings from app config.

    Returns:
        RedisSettings configured for Upstash Redis.
    """
    from worker.app.config import get_settings
    return RedisSettings.from_dsn(get_settings().arq_redis_url)


from worker.jobs.generation_jobs import run_generation_job
from worker.jobs.notion_jobs import run_notion_staging_job
from worker.jobs.scoring_jobs import run_scoring_pipeline
from worker.jobs.triage_jobs import run_triage_job


async def ping(ctx: dict) -> str:
    """Example ARQ job that proves the worker is running.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        The string 'pong'.

    Estimated runtime: <1s
    Retry behavior: None (example job)
    Failure mode: Logs error, no downstream impact
    """
    logger.info("ping job executed")
    return "pong"


class WorkerSettings:
    """ARQ worker settings.

    Configures the Redis connection and registers available job functions.
    Discovery pollers run on cron schedules per PRD Section 2:
    - RSS: every 4 hours
    - Reddit: every 1 hour
    - HN: every 1 hour
    - Twitter: every 2 hours
    """

    redis_settings = _build_redis_settings()

    functions = [ping, poll_rss, poll_reddit, poll_hn, poll_twitter, run_scoring_pipeline, run_triage_job, run_generation_job, run_notion_staging_job]

    cron_jobs = [
        cron(poll_rss, hour={0, 4, 8, 12, 16, 20}, minute=0),
        cron(poll_reddit, minute=15),
        cron(poll_hn, minute=30),
        cron(poll_twitter, hour={1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23}, minute=45),
    ]
