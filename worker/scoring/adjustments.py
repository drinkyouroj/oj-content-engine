"""
Scoring adjustments — apply per-keyword tweaks from the scoring_adjustments table.

Implements PRD Section 3 (Scoring Adjustments).
Justin creates adjustments from the review UI to fine-tune how specific
keywords/topics affect scoring dimensions. Each adjustment adds -20 to +20
to a named dimension. All values are clamped to 0-100 after application.

Inputs:
    - Current scores dict (dimension name -> int).
    - Signal ORM instance (title, body_preview for keyword matching).
    - AsyncSession for querying the scoring_adjustments table.

Outputs:
    - Modified scores dict with adjustments applied and values clamped 0-100.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.scoring_adjustment import ScoringAdjustment


async def apply_adjustments(
    scores: dict[str, int],
    signal: Any,
    session: AsyncSession,
) -> dict[str, int]:
    """Apply keyword-based scoring adjustments from the database.

    For each scoring_adjustment row whose keyword appears (case-insensitive
    substring match) in the signal's title or body_preview, adds the
    adjustment value to the corresponding dimension. All resulting values
    are clamped to the 0-100 range.

    Args:
        scores: Current scoring dimensions dict (mutated in place and returned).
        signal: Signal ORM instance with title and body_preview attributes.
        session: Async database session.

    Returns:
        The same scores dict with adjustments applied and values clamped.
    """
    stmt = select(ScoringAdjustment)
    result = await session.execute(stmt)
    adjustments = result.scalars().all()

    if not adjustments:
        return scores

    text = (signal.title or "").lower()
    if signal.body_preview:
        text += " " + signal.body_preview.lower()

    for adj in adjustments:
        keyword_lower = adj.keyword.lower()
        if keyword_lower in text:
            dimension = adj.dimension
            if dimension in scores:
                scores[dimension] = max(0, min(100, scores[dimension] + adj.adjustment))

    return scores
