"""
ARQ job for topic triage.

Wraps the triage engine in an ARQ-compatible async function.
Registered in WorkerSettings.functions.

Implements PRD Section 3 (Topic Triage Rubric — batch application).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory

logger = logging.getLogger(__name__)


async def _get_session() -> tuple[AsyncSession, AsyncEngine]:
    """Create a one-shot async database session for the job.

    Returns:
        Tuple of (AsyncSession, AsyncEngine).
    """
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    session = session_factory()
    return session, engine


async def run_triage_job(ctx: dict) -> dict[str, int]:
    """ARQ job: run triage on all unprocessed scored signals.

    Applies hard gates and threshold logic to create Topic rows.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Dictionary with counts: {"queued": N, "review": N, "archived": N}.

    Estimated runtime: <1s (pure computation, no external calls).
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Logs error; does not block other jobs.
    """
    from worker.triage.engine import run_triage

    session, engine = await _get_session()
    try:
        counts = await run_triage(session)
        logger.info("Triage job complete: %s", counts)
        return counts
    finally:
        await session.close()
        await engine.dispose()
