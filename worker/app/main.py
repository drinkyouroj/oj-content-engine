"""
FastAPI application for the OJ Content Engine worker.

Provides a /health endpoint for Railway health checks. The application
lifecycle manages database and Redis connections.

Implements PRD Section 8 (Worker Layer).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from arq.connections import RedisSettings
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy import update as sa_update

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory
from worker.app.logging_config import setup_logging

# Configure structured logging before anything else logs
setup_logging()

logger = logging.getLogger(__name__)

# Module-level state populated during lifespan
_engine = None
_session_factory = None
_redis_settings = None
_settings = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database engine and Redis connection pool lifecycle.

    Creates connections on startup, closes them on shutdown.
    """
    global _engine, _session_factory, _redis_settings, _settings

    _settings = get_settings()
    _engine = make_engine(_settings.database_url)
    _session_factory = make_session_factory(_engine)
    _redis_settings = RedisSettings.from_dsn(_settings.arq_redis_url)

    logger.info(
        "Worker started",
        extra={
            "event": "startup",
            "component": "fastapi",
            "database": bool(_engine),
            "redis": bool(_redis_settings),
        },
    )
    yield

    await _engine.dispose()
    _engine = None
    _session_factory = None
    _redis_settings = None
    _settings = None
    logger.info("Worker stopped", extra={"event": "shutdown", "component": "fastapi"})


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
    if not x_worker_secret or not _settings or x_worker_secret != _settings.worker_secret:
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


@app.post("/api/suggest-theses/{topic_id}")
async def suggest_theses_endpoint(
    topic_id: UUID,
    x_worker_secret: str = Header(None),
):
    """Generate 3-5 thesis suggestions for a topic.

    Fetches source article, combines with score data, calls Claude Haiku.
    Requires x-worker-secret header for authentication.

    Estimated runtime: 5-15s (article fetch + LLM call).
    Failure mode: returns error JSON, does not affect topic state.

    Args:
        topic_id: UUID of the topic to generate thesis suggestions for.
        x_worker_secret: Shared secret from the x-worker-secret header.

    Returns:
        JSON with a list of thesis strings under the key "theses".

    Raises:
        HTTPException 401: If the secret is missing or incorrect.
        HTTPException 503: If the session factory is not yet initialised.
        HTTPException 404: If the topic does not exist.
        HTTPException 500: If LLM generation fails.
    """
    if not x_worker_secret or not _settings or x_worker_secret != _settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")

    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Worker not ready")

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from worker.app.models.topic import Topic
    from worker.app.models.scored_signal import ScoredSignal
    from worker.generation.thesis_suggestions import suggest_theses
    from worker.generation.llm_client import LLMClient

    async with _session_factory() as session:
        result = await session.execute(
            select(Topic)
            .where(Topic.id == topic_id)
            .options(
                selectinload(Topic.scored_signal).selectinload(ScoredSignal.signal),
                selectinload(Topic.signal),
            )
        )
        topic = result.scalars().first()

    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    client = LLMClient(
        anthropic_api_key=_settings.anthropic_api_key,
        groq_api_key=_settings.groq_api_key,
    )

    try:
        theses = await suggest_theses(topic, client)
        return {"theses": theses}
    except Exception as exc:
        logger.exception("Failed to generate thesis suggestions for %s", topic_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/generate-social/{topic_id}/{platform}")
async def generate_social_endpoint(
    topic_id: UUID,
    platform: str,
    x_worker_secret: str = Header(None),
):
    """Generate social platform content derived from the Substack article.

    Fetches the topic and its Substack draft, then calls Claude Haiku 4.5 to
    generate content for the requested social platform using the Substack
    article as source context. This is a synchronous call that blocks until
    generation completes (estimated 5-15s).

    Called by the Vercel dashboard when Justin clicks a per-platform "Generate"
    button. Only available after a Substack draft exists for the topic.

    Estimated runtime: 5-15s (LLM call with Haiku 4.5).
    Failure mode: returns error JSON, does not affect topic status.

    Args:
        topic_id: UUID of the topic.
        platform: Target platform: "twitter", "linkedin", or "instagram".
        x_worker_secret: Shared secret from the x-worker-secret header.

    Returns:
        JSON with the created draft ID and platform.

    Raises:
        HTTPException 401: If the secret is missing or incorrect.
        HTTPException 400: If the platform is invalid or not a social platform.
        HTTPException 404: If the topic or Substack draft is not found.
        HTTPException 500: If LLM generation fails.
    """
    if not x_worker_secret or not _settings or x_worker_secret != _settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")

    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Worker not ready")

    valid_platforms = {"twitter", "linkedin", "instagram"}
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform '{platform}'. Must be one of: {', '.join(sorted(valid_platforms))}",
        )

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from worker.app.models.content_draft import ContentDraft, Platform as PlatformEnum
    from worker.app.models.scored_signal import ScoredSignal
    from worker.app.models.topic import Topic
    from worker.generation.engine import generate_social_for_topic
    from worker.generation.llm_client import LLMClient

    async with _session_factory() as session:
        # Fetch topic with signal data
        result = await session.execute(
            select(Topic)
            .where(Topic.id == topic_id)
            .options(
                selectinload(Topic.scored_signal).selectinload(ScoredSignal.signal),
                selectinload(Topic.signal),
            )
        )
        topic = result.scalars().first()

        if topic is None:
            raise HTTPException(status_code=404, detail="Topic not found")

        # Fetch the Substack draft for this topic
        draft_result = await session.execute(
            select(ContentDraft)
            .where(ContentDraft.topic_id == topic_id)
            .where(ContentDraft.platform == PlatformEnum.SUBSTACK)
        )
        substack_draft = draft_result.scalars().first()

        if substack_draft is None:
            raise HTTPException(
                status_code=404,
                detail="No Substack draft found. Generate Substack content first.",
            )

        platform_enum = PlatformEnum(platform)

        client = LLMClient(
            anthropic_api_key=_settings.anthropic_api_key,
            groq_api_key=_settings.groq_api_key,
        )

        try:
            draft = await generate_social_for_topic(
                topic=topic,
                platform=platform_enum,
                substack_content=substack_draft.content,
                session=session,
                llm_client=client,
            )
            await session.commit()
            return {"draft_id": str(draft.id), "platform": platform}
        except Exception as exc:
            logger.exception(
                "Failed to generate %s content for topic %s", platform, topic_id
            )
            raise HTTPException(status_code=500, detail=str(exc))


class ResearchRequest(BaseModel):
    """Request body for the /api/research endpoint."""

    query: str


@app.post("/api/research")
async def research_endpoint(
    body: ResearchRequest,
    x_worker_secret: str = Header(None),
):
    """Search existing signals + Brave Search for topic research.

    Combines database full-text search of existing signals with live Brave
    web search results, deduplicates, and returns a merged list. Used by the
    Vercel research UI to let Justin explore topics before creating them.

    Estimated runtime: 2-5s (DB query + external HTTP call).
    Failure mode: returns partial results with warnings if Brave is unavailable.

    Args:
        body: ResearchRequest containing the search query string.
        x_worker_secret: Shared secret from the x-worker-secret header.

    Returns:
        JSON with "results" (list of research items) and "warnings" (list of strings).

    Raises:
        HTTPException 401: If the secret is missing or incorrect.
        HTTPException 503: If the session factory is not yet initialised.
    """
    if not x_worker_secret or not _settings or x_worker_secret != _settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")
    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Worker not ready")

    from worker.discovery.research import (
        merge_and_deduplicate,
        search_existing_signals,
        search_web,
    )

    warnings: list[str] = []

    async with _session_factory() as session:
        db_results = await search_existing_signals(body.query, session)

    web_results = await search_web(body.query, _settings.brave_search_api_key)
    if not web_results and _settings.brave_search_api_key:
        warnings.append("Brave Search unavailable")

    merged = merge_and_deduplicate(db_results, web_results)
    return {"results": merged, "warnings": warnings}


class ArticleInput(BaseModel):
    """A single article selected from research results."""

    title: str
    url: str
    body_preview: str | None = None
    source: str = "web"


class CreateTopicsRequest(BaseModel):
    """Request body for the /api/create-topics endpoint."""

    articles: list[ArticleInput]


@app.post("/api/create-topics")
async def create_topics_endpoint(
    body: CreateTopicsRequest,
    x_worker_secret: str = Header(None),
):
    """Create topics directly from selected research articles, skipping scoring.

    For each article, creates a Signal (or reuses an existing one based on
    dedup hash) and then creates a Topic in QUEUED status. Articles that
    already have a Topic are skipped. This allows the research UI to fast-track
    manually selected articles into the content generation pipeline.

    Estimated runtime: <500ms (DB reads + writes only).
    Failure mode: 401 on bad secret, 503 if not ready, 500 on DB error.

    Args:
        body: CreateTopicsRequest containing a list of articles.
        x_worker_secret: Shared secret from the x-worker-secret header.

    Returns:
        JSON with "created" count, "skipped" count, and "topic_ids" list.

    Raises:
        HTTPException 401: If the secret is missing or incorrect.
        HTTPException 503: If the session factory is not yet initialised.
    """
    if not x_worker_secret or not _settings or x_worker_secret != _settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")
    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Worker not ready")

    from sqlalchemy import select

    from worker.app.models.scored_signal import ScoredSignal
    from worker.app.models.signal import Signal, SignalSource
    from worker.app.models.topic import Topic, TopicStatus
    from worker.discovery.dedup import compute_dedup_hash, normalize_url

    created = 0
    skipped = 0
    topic_ids: list[str] = []

    async with _session_factory() as session:
        for article in body.articles:
            normalized = normalize_url(article.url)
            dedup_hash = compute_dedup_hash(normalized)

            # Check for existing signal — reuse it if found
            existing = await session.execute(
                select(Signal.id).where(Signal.dedup_hash == dedup_hash)
            )
            existing_signal_id = existing.scalar_one_or_none()

            if existing_signal_id is not None:
                # Signal exists — check if a topic already exists for it
                existing_topic = await session.execute(
                    select(Topic.id).where(
                        (Topic.signal_id == existing_signal_id)
                        | (
                            Topic.scored_signal_id.in_(
                                select(ScoredSignal.id).where(
                                    ScoredSignal.signal_id == existing_signal_id
                                )
                            )
                        )
                    )
                )
                if existing_topic.scalar_one_or_none() is not None:
                    skipped += 1
                    continue

                signal_id = existing_signal_id
            else:
                signal = Signal(
                    source=SignalSource.MANUAL,
                    url=article.url,
                    title=article.title,
                    body_preview=(article.body_preview or "")[:500] or None,
                    discovered_at=datetime.now(timezone.utc),
                    source_metrics=None,
                    dedup_hash=dedup_hash,
                )
                session.add(signal)
                await session.flush()
                signal_id = signal.id

            topic = Topic(
                signal_id=signal_id,
                scored_signal_id=None,
                status=TopicStatus.QUEUED,
                queued_at=datetime.now(timezone.utc),
            )
            session.add(topic)
            await session.flush()

            topic_ids.append(str(topic.id))
            created += 1

        await session.commit()

    return {"created": created, "skipped": skipped, "topic_ids": topic_ids}


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
