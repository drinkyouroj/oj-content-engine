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
import time

from sqlalchemy import select

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
    t0 = time.monotonic()
    logger.info("Starting scoring pipeline", extra={"event": "job_start", "stage": "scoring"})

    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    scored_count = 0
    error_count = 0

    async with session_factory() as session:
        # Find signals without a scored_signal row
        scored_subq = select(ScoredSignal.signal_id).subquery()
        stmt = select(Signal).where(Signal.id.notin_(select(scored_subq)))
        result = await session.execute(stmt)
        unscored_signals = result.scalars().all()

        total = len(unscored_signals)
        logger.info(
            "Found %d unscored signals", total,
            extra={"event": "scoring_batch", "stage": "scoring", "unscored": total},
        )

        for i, signal in enumerate(unscored_signals, 1):
            try:
                await score_signal(
                    signal_id=signal.id,
                    session=session,
                    llm_api_key=settings.groq_api_key or settings.anthropic_api_key,
                )
                scored_count += 1
                logger.debug(
                    "Scored signal %d/%d: %s", i, total, signal.id,
                    extra={"event": "signal_scored", "stage": "scoring", "signal_id": str(signal.id), "progress": f"{i}/{total}"},
                )
            except Exception:  # noqa: BLE001
                error_count += 1
                logger.exception(
                    "Failed to score signal %s (%d/%d)", signal.id, i, total,
                    extra={"event": "scoring_error", "stage": "scoring", "signal_id": str(signal.id)},
                )

        await session.commit()

    await engine.dispose()

    elapsed = round(time.monotonic() - t0, 2)
    logger.info(
        "Scoring pipeline complete: %d scored, %d errors in %.2fs",
        scored_count, error_count, elapsed,
        extra={
            "event": "job_complete", "stage": "scoring",
            "scored": scored_count, "errors": error_count, "elapsed_s": elapsed,
        },
    )
    return scored_count
