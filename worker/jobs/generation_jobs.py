"""ARQ job for content generation.

Wraps the generation engine in an ARQ-compatible async function.
Processes all queued/approved topics, generates a Substack draft per topic,
then triggers Notion staging.

Social platform content (Twitter, LinkedIn, Instagram) is generated
on-demand via the /api/generate-social endpoint when the reviewer
explicitly requests it from the dashboard.

Implements PRD Section 4 (Content Generation Pipeline).
"""
from __future__ import annotations

import logging
import time

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
    """ARQ job: generate Substack drafts for all queued/approved topics.

    Queries topics with status='queued' (auto-approved) or status='review'
    with thesis provided (manually approved), generates a Substack draft
    for each, then calls Notion staging.

    Social content (Twitter, LinkedIn, Instagram) is NOT generated here.
    Those are generated on-demand via the /api/generate-social endpoint.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Dictionary with counts: {"topics_processed": N, "drafts_created": N, "errors": N}.

    Estimated runtime: 15-60s per topic (1 LLM call + 1 critique).
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Per-topic errors logged; does not block other topics.
    """
    from worker.jobs.notion_jobs import run_notion_staging_job

    t0 = time.monotonic()
    logger.info("Starting generation job", extra={"event": "job_start", "stage": "generation"})

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
            elapsed = round(time.monotonic() - t0, 2)
            logger.info(
                "No queued topics to generate (%.2fs)", elapsed,
                extra={"event": "job_complete", "stage": "generation", "topics_processed": 0, "elapsed_s": elapsed},
            )
            return {"topics_processed": 0, "drafts_created": 0, "errors": 0}

        logger.info(
            "Found %d topics to generate", len(topics),
            extra={"event": "generation_batch", "stage": "generation", "topics": len(topics)},
        )

        client = LLMClient(
            groq_api_key=settings.groq_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )

        counts = {"topics_processed": 0, "drafts_created": 0, "errors": 0}

        for i, topic in enumerate(topics, 1):
            topic_t0 = time.monotonic()
            try:
                drafts = await generate_for_topic(topic, session, client)
                counts["topics_processed"] += 1
                counts["drafts_created"] += len(drafts)
                topic_elapsed = round(time.monotonic() - topic_t0, 2)
                logger.info(
                    "Generated %d drafts for topic %s (%d/%d) in %.2fs",
                    len(drafts), topic.id, i, len(topics), topic_elapsed,
                    extra={
                        "event": "topic_generated", "stage": "generation",
                        "topic_id": str(topic.id), "drafts": len(drafts),
                        "progress": f"{i}/{len(topics)}", "elapsed_s": topic_elapsed,
                    },
                )
            except Exception:
                counts["errors"] += 1
                logger.exception(
                    "Failed to generate for topic %s (%d/%d)", topic.id, i, len(topics),
                    extra={"event": "generation_error", "stage": "generation", "topic_id": str(topic.id)},
                )

        await session.commit()

        elapsed = round(time.monotonic() - t0, 2)
        logger.info(
            "Generation complete: %d topics, %d drafts, %d errors in %.2fs",
            counts["topics_processed"], counts["drafts_created"], counts["errors"], elapsed,
            extra={
                "event": "job_complete", "stage": "generation",
                "topics_processed": counts["topics_processed"],
                "drafts_created": counts["drafts_created"],
                "errors": counts["errors"],
                "elapsed_s": elapsed,
            },
        )

        # Trigger Notion staging
        await run_notion_staging_job(ctx)

        return counts
    finally:
        await session.close()
        await engine.dispose()
