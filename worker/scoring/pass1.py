"""
Pass 1 — Rule-based scoring for Signal Strength, Timing Window, and Community Resonance.

Implements PRD Section 3 (Topic Triage Rubric), Pass 1.
These three dimensions are computed without any LLM calls, using only database
queries, timestamps, and keyword matching. This keeps Pass 1 zero-cost and fast.

Inputs:
    - Signal ORM instance (title, body_preview, discovered_at, dedup_hash, source).
    - AsyncSession for database queries (signal_strength corroboration check).

Outputs:
    - Dictionary with keys: signal_strength, timing_window, community_resonance.
      Each value is an integer 0-100.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.signal import Signal
from worker.scoring.rubric import RESONANCE_SCORES, RESONANCE_TAXONOMY


async def score_signal_strength(signal: Signal, session: AsyncSession) -> int:
    """Score signal strength based on cross-source corroboration.

    Queries the DB for other signals with the same dedup_hash or similar titles
    discovered in the last 7 days, then counts distinct sources.

    Args:
        signal: The signal to score.
        session: Async database session for querying corroborating signals.

    Returns:
        Integer score 0-100:
          - 1 source  = 10
          - 2 sources = 40
          - 3+ same-platform = 70
          - 3+ cross-platform = 100
    """
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Find signals with the same dedup_hash or matching title (case-insensitive)
    stmt = (
        select(Signal.source)
        .where(
            Signal.id != signal.id,
            Signal.discovered_at >= seven_days_ago,
            (Signal.dedup_hash == signal.dedup_hash)
            | (func.lower(Signal.title) == func.lower(signal.title)),
        )
    )
    result = await session.execute(stmt)
    corroborating_sources = {row[0] for row in result.fetchall()}

    # Include the signal's own source
    all_sources = corroborating_sources | {signal.source}
    distinct_count = len(all_sources)

    if distinct_count >= 3:
        # Cross-platform means more than one unique source enum value
        if len(all_sources) >= 3:
            return 100
        return 70
    if distinct_count == 2:
        return 40
    return 10


def score_timing_window(signal: Signal) -> int:
    """Score timing window based on signal age.

    Note: The conditional cap (100 -> 70 when novelty < 50) is applied later
    in pipeline.py, not here. This function returns the raw timing score.

    Args:
        signal: The signal to score (uses discovered_at).

    Returns:
        Integer score 0-100:
          - < 48 hours    = 100
          - 48-72 hours   = 80
          - 3-7 days      = 50
          - > 7 days      = 30
    """
    now = datetime.now(timezone.utc)
    age = now - signal.discovered_at

    if age < timedelta(hours=48):
        return 100
    if age < timedelta(hours=72):
        return 80
    if age <= timedelta(days=7):
        return 50
    return 30


def score_community_resonance(signal: Signal) -> int:
    """Score community resonance via keyword matching against taxonomy.

    Performs case-insensitive substring matching of the signal's title and
    body_preview against the resonance taxonomy. Checks categories in priority
    order (core -> direct -> adjacent) and returns the highest match.

    Args:
        signal: The signal to score (uses title and body_preview).

    Returns:
        Integer score 0-100 based on the highest matching taxonomy tier,
        or 0 if no keywords match.
    """
    text = (signal.title or "").lower()
    if signal.body_preview:
        text += " " + signal.body_preview.lower()

    # Check in priority order — return on first match for highest tier
    for tier in ("core", "direct", "adjacent"):
        keywords = RESONANCE_TAXONOMY[tier]["keywords"]
        for keyword in keywords:
            if keyword in text:
                return RESONANCE_SCORES[tier]

    return RESONANCE_SCORES["none"]


async def compute_pass1_scores(signal: Signal, session: AsyncSession) -> dict[str, int]:
    """Run all Pass 1 scoring functions and return results.

    Args:
        signal: The signal to score.
        session: Async database session.

    Returns:
        Dictionary with keys: signal_strength, timing_window, community_resonance.
        Each value is an integer 0-100.
    """
    strength = await score_signal_strength(signal, session)
    timing = score_timing_window(signal)
    resonance = score_community_resonance(signal)

    return {
        "signal_strength": strength,
        "timing_window": timing,
        "community_resonance": resonance,
    }
