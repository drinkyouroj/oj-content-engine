"""
FastAPI application for the OJ Content Engine worker.

Provides a /health endpoint for Railway health checks. The application
lifecycle manages database and Redis connections.

Implements PRD Section 8 (Worker Layer).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from arq.connections import RedisSettings
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy import update as sa_update

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory

logger = logging.getLogger(__name__)

# Module-level state populated during lifespan
_engine = None
_session_factory = None
_redis_settings = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database engine and Redis connection pool lifecycle.

    Creates connections on startup, closes them on shutdown.
    """
    global _engine, _session_factory, _redis_settings

    settings = get_settings()
    _engine = make_engine(settings.database_url)
    _session_factory = make_session_factory(_engine)
    _redis_settings = RedisSettings.from_dsn(settings.arq_redis_url)

    logger.info("Worker started — database and Redis connections ready")
    yield

    await _engine.dispose()
    _engine = None
    _session_factory = None
    _redis_settings = None
    logger.info("Worker stopped — connections closed")


app = FastAPI(
    title="OJ Content Engine Worker",
    version="0.1.0",
    lifespan=lifespan,
)


async def check_db() -> bool:
    """Check database connectivity by executing a simple query.

    Returns:
        True if the database is reachable, False otherwise.
    """
    if _session_factory is None:
        return False
    try:
        async with _session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database health check failed")
        return False


async def check_redis() -> bool:
    """Check Redis connectivity via direct redis-py connection.

    Uses redis-py directly instead of arq.create_pool to avoid
    repeated retry delays on health checks.

    Returns:
        True if Redis is reachable, False otherwise.
    """
    try:
        from redis.asyncio import Redis
        settings = get_settings()
        r = Redis.from_url(settings.arq_redis_url, decode_responses=True)
        pong = await r.ping()
        await r.aclose()
        return pong
    except Exception:
        logger.exception("Redis health check failed")
        return False


@app.post("/api/regenerate/{topic_id}")
async def regenerate_topic(
    topic_id: UUID,
    x_worker_secret: str = Header(None),
):
    """Regenerate content for a specific topic.

    Resets topic status to 'queued' and enqueues a generation job via ARQ.
    Called by the Vercel approval UI when the reviewer requests new drafts,
    optionally after saving a thesis via /api/thesis.

    Requires the x-worker-secret header to match WORKER_SECRET.

    Estimated runtime: <200ms (DB write + Redis enqueue only; generation is async).
    Retry behaviour: not retried — the caller (Vercel route) surfaces errors directly.
    Failure mode: 401 on bad secret, 503 if lifespan not complete, 500 on DB/Redis error.

    Args:
        topic_id: UUID of the topic to regenerate.
        x_worker_secret: Shared secret from the x-worker-secret header.

    Returns:
        JSON with status, topic_id, and ARQ job_id.

    Raises:
        HTTPException 401: If the secret is missing or incorrect.
        HTTPException 503: If the session factory is not yet initialised.
    """
    settings = get_settings()
    if not x_worker_secret or x_worker_secret != settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")

    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Worker not ready")

    from worker.app.models.topic import Topic, TopicStatus

    async with _session_factory() as session:
        await session.execute(
            sa_update(Topic).where(Topic.id == topic_id).values(status=TopicStatus.QUEUED)
        )
        await session.commit()

    # Enqueue ARQ generation job using the lifespan-managed Redis settings
    from arq.connections import ArqRedis, create_pool

    pool: ArqRedis = await create_pool(_redis_settings)
    job = await pool.enqueue_job("run_generation_job")
    await pool.close()

    return {"status": "queued", "topic_id": str(topic_id), "job_id": job.job_id}


@app.get("/health")
async def health():
    """Health check endpoint for Railway.

    Returns:
        JSON with status, database, and redis connectivity.
        200 if all healthy, 503 if any service is down.
    """
    db_ok = await check_db()
    redis_ok = await check_redis()
    healthy = db_ok and redis_ok

    body = {"status": "healthy" if healthy else "unhealthy", "database": db_ok, "redis": redis_ok}
    return JSONResponse(content=body, status_code=200 if healthy else 503)
