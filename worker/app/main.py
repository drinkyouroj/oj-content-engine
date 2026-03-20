"""
FastAPI application for the OJ Content Engine worker.

Provides a /health endpoint for Railway health checks. The application
lifecycle manages database and Redis connections.

Implements PRD Section 8 (Worker Layer).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

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
