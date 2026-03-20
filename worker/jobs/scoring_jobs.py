"""
ARQ job for the signal scoring pipeline.

Implements PRD Section 3 (Topic Triage Rubric).
Finds all signals that have not yet been scored (no corresponding
scored_signals row) and runs them through the two-pass scoring pipeline.
Triggered by discovery jobs or manually — not on a cron schedule.

Estimated runtime: ~2-10s per signal (Pass 2 LLM call dominates).
Retry behavior: Individual signal failures are logged and skipped;
    the job itself does not retry.
Failure mode: Logs errors per signal, returns count of successfully scored.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory
from worker.app.models.scored_signal import ScoredSignal
from worker.app.models.signal import Signal
from worker.scoring.pipeline import score_signal

logger = logging.getLogger(__name__)


async def run_scoring_pipeline(ctx: dict) -> int:
    """Score all unscored signals.

    Queries for signals that lack a scored_signals row, then runs each
    through the full scoring pipeline (Pass 1 -> adjustments -> Pass 2).

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Count of signals successfully scored.

    Estimated runtime: ~2-10s per signal (dominated by Pass 2 LLM call).
    Retry behavior: Individual signal failures are logged and skipped.
    Failure mode: Logs errors, returns partial count. Does not raise.
    """
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    scored_count = 0

    async with session_factory() as session:
        # Find signals without a scored_signal row
        scored_subq = select(ScoredSignal.signal_id).subquery()
        stmt = select(Signal).where(Signal.id.notin_(select(scored_subq)))
        result = await session.execute(stmt)
        unscored_signals = result.scalars().all()

        logger.info("Found %d unscored signals", len(unscored_signals))

        for signal in unscored_signals:
            try:
                await score_signal(
                    signal_id=signal.id,
                    session=session,
                    anthropic_api_key=settings.anthropic_api_key,
                )
                scored_count += 1
            except Exception:  # noqa: BLE001
                logger.exception("Failed to score signal %s", signal.id)

        await session.commit()

    await engine.dispose()

    logger.info("Scoring pipeline complete: %d signals scored", scored_count)
    return scored_count
