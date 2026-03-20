"""ARQ job for content generation.

Wraps the generation engine in an ARQ-compatible async function.
Processes all queued/approved topics, generates 4 platform drafts per topic,
then triggers Notion staging.

Implements PRD Section 4 (Content Generation Pipeline).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory
from worker.app.models.scored_signal import ScoredSignal
from worker.app.models.topic import Topic, TopicStatus
from worker.generation.engine import generate_for_topic
from worker.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


async def _get_session() -> tuple[AsyncSession, AsyncEngine]:
    """Create a one-shot async database session for the job."""
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    session = session_factory()
    return session, engine


async def run_generation_job(ctx: dict) -> dict[str, int]:
    """ARQ job: generate content drafts for all queued/approved topics.

    Queries topics with status='queued' (auto-approved) or status='review'
    with thesis provided (manually approved), generates 4 platform drafts
    for each, then calls Notion staging.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Dictionary with counts: {"topics_processed": N, "drafts_created": N, "errors": N}.

    Estimated runtime: 30-120s per topic (4 LLM calls + 1 critique).
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Per-topic errors logged; does not block other topics.
    """
    from worker.jobs.notion_jobs import run_notion_staging_job

    settings = get_settings()
    session, engine = await _get_session()

    try:
        stmt = select(Topic).where(
            (Topic.status == TopicStatus.QUEUED)
            | ((Topic.status == TopicStatus.REVIEW) & (Topic.thesis_provided == True))  # noqa: E712
        ).options(
            selectinload(Topic.scored_signal).selectinload(ScoredSignal.signal),
        )
        result = await session.execute(stmt)
        topics = result.scalars().all()

        if not topics:
            logger.info("No queued topics to generate")
            return {"topics_processed": 0, "drafts_created": 0, "errors": 0}

        client = LLMClient(
            groq_api_key=settings.groq_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )

        counts = {"topics_processed": 0, "drafts_created": 0, "errors": 0}

        for topic in topics:
            try:
                drafts = await generate_for_topic(topic, session, client)
                counts["topics_processed"] += 1
                counts["drafts_created"] += len(drafts)
            except Exception:
                logger.exception("Failed to generate for topic %s", topic.id)
                counts["errors"] += 1

        await session.commit()
        logger.info("Generation complete: %s", counts)

        # Trigger Notion staging
        await run_notion_staging_job(ctx)

        return counts
    finally:
        await session.close()
        await engine.dispose()
