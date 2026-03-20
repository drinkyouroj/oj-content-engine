"""
Scoring pipeline orchestrator — coordinates Pass 1, adjustments, and Pass 2.

Implements PRD Section 3 (Topic Triage Rubric).
This is the main entry point for scoring a single signal. It runs the two-pass
scoring process, applies adjustments, computes the weighted composite score,
and persists the result as a ScoredSignal row.

Inputs:
    - signal_id (UUID) identifying the signal to score.
    - AsyncSession for database operations.
    - Anthropic API key for Pass 2 LLM calls.

Outputs:
    - ScoredSignal ORM instance persisted to the database.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.scored_signal import ScoredSignal, ScoringStatus
from worker.app.models.signal import Signal
from worker.scoring.adjustments import apply_adjustments
from worker.scoring.pass1 import compute_pass1_scores
from worker.scoring.pass2 import LLMScoringError, score_with_llm
from worker.scoring.rubric import PASS1_PREFILTER_THRESHOLD, WEIGHTS

logger = logging.getLogger(__name__)


async def score_signal(
    signal_id: uuid.UUID,
    session: AsyncSession,
    anthropic_api_key: str,
) -> ScoredSignal:
    """Score a single signal through the full two-pass pipeline.

    Pipeline steps:
      1. Load signal from DB.
      2. Run Pass 1 (signal_strength, timing_window, community_resonance).
      3. Apply scoring adjustments from DB.
      4. Compute Pass 1 pre-filter score (weighted sum of Pass 1 dims only).
      5. If pre-filter <= PASS1_PREFILTER_THRESHOLD, persist and return early.
      6. Run Pass 2 (depth_potential, novelty, brand_angle_availability).
      7. Apply timing conditional cap: if timing == 100 and novelty < 50, cap at 70.
      8. Combine all 6 scores into score_breakdown JSONB.
      9. Compute composite_score as weighted sum of all 6 dimensions.
     10. Create/update ScoredSignal row with status='scored'.
     11. Return ScoredSignal.

    Args:
        signal_id: UUID of the signal to score.
        session: Async database session.
        anthropic_api_key: Anthropic API key for Pass 2.

    Returns:
        ScoredSignal instance with scoring results persisted.

    Raises:
        ValueError: If the signal_id does not exist in the database.
    """
    # Step 1: Load signal
    stmt = select(Signal).where(Signal.id == signal_id)
    result = await session.execute(stmt)
    signal = result.scalar_one_or_none()
    if signal is None:
        raise ValueError(f"Signal {signal_id} not found")

    # Step 2: Pass 1
    scores = await compute_pass1_scores(signal, session)
    pass1_completed = datetime.now(timezone.utc)

    # Step 3: Apply adjustments to Pass 1 scores
    scores = await apply_adjustments(scores, signal, session)

    # Step 4: Pre-filter check (weighted sum of Pass 1 dimensions only)
    pass1_dims = ("signal_strength", "timing_window", "community_resonance")
    pass1_weighted = sum(scores[d] * WEIGHTS[d] for d in pass1_dims)
    # Normalize: divide by sum of pass1 weights to get 0-100 scale
    pass1_weight_sum = sum(WEIGHTS[d] for d in pass1_dims)
    prefilter_score = pass1_weighted / pass1_weight_sum if pass1_weight_sum else 0

    # Step 5: Early exit if below pre-filter threshold
    if prefilter_score <= PASS1_PREFILTER_THRESHOLD:
        logger.info(
            "Signal %s pre-filtered with score %.1f (<= %d)",
            signal_id,
            prefilter_score,
            PASS1_PREFILTER_THRESHOLD,
        )
        score_breakdown = {
            "signal_strength": scores["signal_strength"],
            "timing_window": scores["timing_window"],
            "community_resonance": scores["community_resonance"],
            "depth_potential": 0,
            "novelty": 0,
            "brand_angle_availability": 0,
        }
        composite = _compute_composite(score_breakdown)
        scored_signal = ScoredSignal(
            signal_id=signal_id,
            score_breakdown=score_breakdown,
            composite_score=composite,
            status=ScoringStatus.SCORED,
            pass1_completed_at=pass1_completed,
        )
        session.add(scored_signal)
        await session.flush()
        return scored_signal

    # Step 6: Pass 2 — LLM scoring
    try:
        pass2_scores = await score_with_llm(signal, anthropic_api_key)
    except LLMScoringError:
        logger.error("LLM scoring failed for signal %s — marking as failed", signal_id)
        scored_signal = ScoredSignal(
            signal_id=signal_id,
            score_breakdown={d: scores.get(d, 0) for d in WEIGHTS},
            composite_score=0,
            status=ScoringStatus.FAILED,
            pass1_completed_at=pass1_completed,
        )
        session.add(scored_signal)
        await session.flush()
        return scored_signal
    pass2_completed = datetime.now(timezone.utc)

    # Merge Pass 2 into scores
    scores.update(pass2_scores)

    # Re-apply adjustments to catch Pass 2 dimension adjustments
    scores = await apply_adjustments(scores, signal, session)

    # Step 7: Timing conditional cap
    if scores["timing_window"] == 100 and scores["novelty"] < 50:
        scores["timing_window"] = 70

    # Step 8: Build score_breakdown
    score_breakdown = {
        "signal_strength": scores["signal_strength"],
        "timing_window": scores["timing_window"],
        "depth_potential": scores["depth_potential"],
        "novelty": scores["novelty"],
        "community_resonance": scores["community_resonance"],
        "brand_angle_availability": scores["brand_angle_availability"],
    }

    # Step 9: Composite score
    composite = _compute_composite(score_breakdown)

    # Step 10: Persist
    scored_signal = ScoredSignal(
        signal_id=signal_id,
        score_breakdown=score_breakdown,
        composite_score=composite,
        status=ScoringStatus.SCORED,
        pass1_completed_at=pass1_completed,
        pass2_completed_at=pass2_completed,
    )
    session.add(scored_signal)
    await session.flush()

    logger.info(
        "Signal %s scored: composite=%.1f, breakdown=%s",
        signal_id,
        composite,
        score_breakdown,
    )

    # Step 11: Return
    return scored_signal


def _compute_composite(score_breakdown: dict[str, int]) -> float:
    """Compute weighted composite score from all 6 dimensions.

    Args:
        score_breakdown: Dictionary mapping dimension names to integer scores.

    Returns:
        Weighted composite score as a float (0-100).
    """
    return sum(
        score_breakdown.get(dim, 0) * weight
        for dim, weight in WEIGHTS.items()
    )
