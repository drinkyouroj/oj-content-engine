"""
Triage engine — mechanical rubric application on scored signals.

Implements PRD Section 3 (Topic Triage Rubric). Pure computation:
applies hard gates, checks composite score thresholds, and creates
Topic rows with the appropriate status.

Inputs:
    - ScoredSignal rows with status='scored' that don't yet have a Topic.
    - Hard gate thresholds and composite score thresholds from rubric.py.

Outputs:
    - Topic rows in the database with status: queued, review, or archived.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.scored_signal import ScoredSignal, ScoringStatus
from worker.app.models.topic import Topic, TopicStatus
from worker.scoring.rubric import THRESHOLD_QUEUE, THRESHOLD_REVIEW

logger = logging.getLogger(__name__)

#: Hard gate: community resonance below this auto-rejects regardless of composite score
HARD_GATE_COMMUNITY_RESONANCE = 20

#: Hard gate: brand angle below this auto-rejects regardless of composite score
HARD_GATE_BRAND_ANGLE = 20


def apply_hard_gates(score_breakdown: dict[str, int]) -> str | None:
    """Check hard gate conditions that auto-reject a signal.

    Args:
        score_breakdown: Dictionary with all 6 scoring dimension values.

    Returns:
        Rejection reason string if a hard gate fails, None if the signal passes.
    """
    resonance = score_breakdown.get("community_resonance", 0)
    brand_angle = score_breakdown.get("brand_angle_availability", 0)

    if resonance < HARD_GATE_COMMUNITY_RESONANCE:
        return f"community_resonance={resonance} < {HARD_GATE_COMMUNITY_RESONANCE}"

    if brand_angle < HARD_GATE_BRAND_ANGLE:
        return f"brand_angle_availability={brand_angle} < {HARD_GATE_BRAND_ANGLE}"

    return None


def determine_topic_status(composite_score: float) -> TopicStatus:
    """Determine the topic status based on composite score thresholds.

    Args:
        composite_score: Weighted composite score (0-100).

    Returns:
        TopicStatus enum value:
        - QUEUED if >= 65 (auto-queue for thesis injection + generation)
        - REVIEW if 55-64 (flagged for Justin's manual review)
        - ARCHIVED if < 55 (logged, not deleted)
    """
    if composite_score >= THRESHOLD_QUEUE:
        return TopicStatus.QUEUED
    if composite_score >= THRESHOLD_REVIEW:
        return TopicStatus.REVIEW
    return TopicStatus.ARCHIVED


async def triage_scored_signal(
    scored_signal: ScoredSignal,
    session: AsyncSession,
) -> Topic:
    """Apply triage rubric to a single scored signal and create a Topic.

    Steps:
    1. Check hard gates (community resonance, brand angle).
    2. If hard gate fails: create Topic with status=ARCHIVED.
    3. If passes: determine status from composite score thresholds.
    4. Create and persist the Topic row.

    Args:
        scored_signal: A ScoredSignal with status='scored'.
        session: Async database session.

    Returns:
        The created Topic instance.
    """
    breakdown = scored_signal.score_breakdown
    composite = float(scored_signal.composite_score)

    # Step 1-2: Hard gates
    rejection = apply_hard_gates(breakdown)
    if rejection is not None:
        topic = Topic(
            scored_signal_id=scored_signal.id,
            status=TopicStatus.ARCHIVED,
            review_decision=f"hard_gate: {rejection}",
        )
        session.add(topic)
        logger.debug(
            "Signal %s archived by hard gate: %s (composite=%.1f)",
            scored_signal.signal_id,
            rejection,
            composite,
        )
        return topic

    # Step 3: Threshold logic
    status = determine_topic_status(composite)

    topic = Topic(
        scored_signal_id=scored_signal.id,
        status=status,
        queued_at=datetime.now(timezone.utc) if status == TopicStatus.QUEUED else None,
    )
    session.add(topic)

    logger.info(
        "Signal %s triaged as %s (composite=%.1f)",
        scored_signal.signal_id,
        status.value,
        composite,
    )
    return topic


async def run_triage(session: AsyncSession) -> dict[str, int]:
    """Triage all scored signals that don't yet have a Topic.

    Queries for ScoredSignals with status='scored' that have no
    corresponding Topic row, and runs triage on each.

    Args:
        session: Async database session.

    Returns:
        Dictionary with counts: {"queued": N, "review": N, "archived": N}.
    """
    # Find scored signals without topics
    existing_topic_ids = select(Topic.scored_signal_id)
    stmt = select(ScoredSignal).where(
        ScoredSignal.status == ScoringStatus.SCORED,
        ScoredSignal.id.not_in(existing_topic_ids),
    )
    result = await session.execute(stmt)
    unprocessed = result.scalars().all()

    counts: dict[str, int] = {"queued": 0, "review": 0, "archived": 0}

    for scored in unprocessed:
        topic = await triage_scored_signal(scored, session)
        counts[topic.status.value] += 1

    await session.commit()

    logger.info(
        "Triage complete: %d queued, %d review, %d archived",
        counts["queued"],
        counts["review"],
        counts["archived"],
    )
    return counts
