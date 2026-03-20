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


class _LazyRedisSettings:
    """Descriptor that defers RedisSettings creation until first access.

    ARQ reads WorkerSettings.redis_settings at worker startup, not at
    import time. This lets tests import WorkerSettings without needing
    env vars configured.
    """

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, objtype=None):
        from worker.app.config import get_settings
        settings = RedisSettings.from_dsn(get_settings().arq_redis_url)
        # Cache on the class so this only runs once
        setattr(objtype, self._name, settings)
        return settings


class WorkerSettings:
    """ARQ worker settings.

    Configures the Redis connection and registers available job functions.
    Future feature branches add their functions to the `functions` list
    and cron_jobs to `cron_jobs`.
    """

    redis_settings = _LazyRedisSettings()

    functions = [ping]
    cron_jobs = []
