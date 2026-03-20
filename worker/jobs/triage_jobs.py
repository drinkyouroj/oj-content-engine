"""
ARQ job for topic triage.

Wraps the triage engine in an ARQ-compatible async function.
Registered in WorkerSettings.functions.

Implements PRD Section 3 (Topic Triage Rubric — batch application).
"""

from __future__ import annotations

import logging
import time

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

    t0 = time.monotonic()
    logger.info("Starting triage", extra={"event": "job_start", "stage": "triage"})

    session, engine = await _get_session()
    try:
        counts = await run_triage(session)
        elapsed = round(time.monotonic() - t0, 2)
        logger.info(
            "Triage complete: queued=%d, review=%d, archived=%d in %.2fs",
            counts.get("queued", 0), counts.get("review", 0), counts.get("archived", 0), elapsed,
            extra={
                "event": "job_complete", "stage": "triage",
                "queued": counts.get("queued", 0),
                "review": counts.get("review", 0),
                "archived": counts.get("archived", 0),
                "elapsed_s": elapsed,
            },
        )
        return counts
    except Exception:
        elapsed = round(time.monotonic() - t0, 2)
        logger.exception(
            "Triage failed after %.2fs", elapsed,
            extra={"event": "job_error", "stage": "triage", "elapsed_s": elapsed},
        )
        raise
    finally:
        await session.close()
        await engine.dispose()
