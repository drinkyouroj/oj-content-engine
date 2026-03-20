"""
ARQ worker configuration and job registry.

Connects to Upstash Redis via ARQ_REDIS_URL. Future feature branches
register their cron functions and jobs here.

Implements PRD Section 8 (ARQ as async task queue).
"""

from __future__ import annotations

import logging

from arq.connections import RedisSettings

logger = logging.getLogger(__name__)


def _build_redis_settings() -> RedisSettings:
    """Build Redis connection settings from app config.

    Returns:
        RedisSettings configured for Upstash Redis.
    """
    from worker.app.config import get_settings
    return RedisSettings.from_dsn(get_settings().arq_redis_url)


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
    Future feature branches add their functions to the `functions` list
    and cron_jobs to `cron_jobs`.
    """

    redis_settings = _build_redis_settings()

    functions = [ping]
    cron_jobs = []
