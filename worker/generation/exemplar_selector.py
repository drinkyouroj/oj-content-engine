"""Vertical-aware voice exemplar selection.

Selects 3-5 voice exemplars from the database, prioritizing exemplars
whose vertical matches the topic's detected vertical. Falls back to
other verticals if insufficient matches.
"""
from __future__ import annotations

import logging
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.voice_exemplar import VoiceExemplar

logger = logging.getLogger(__name__)

_MIN_EXEMPLARS = 3
_MAX_EXEMPLARS = 5


async def select_exemplars(
    session: AsyncSession,
    platform: str,
    vertical: str,
) -> list[VoiceExemplar]:
    """Select 3-5 voice exemplars prioritized by vertical match.

    Selection logic:
    1. Query all active exemplars for the target platform.
    2. Split into matching-vertical and other-vertical groups.
    3. If >= 3 matches, randomly select 3-5 from matches.
    4. If < 3 matches, take all matches + fill from others.
    5. If zero total, return empty list.

    Args:
        session: Async database session.
        platform: Target platform (substack, twitter, etc.).
        vertical: Topic's detected vertical.

    Returns:
        List of VoiceExemplar instances (0 to 5).
    """
    stmt = select(VoiceExemplar).where(
        VoiceExemplar.active == True,  # noqa: E712
        VoiceExemplar.platform == platform,
    )
    result = await session.execute(stmt)
    all_exemplars = result.scalars().all()

    if not all_exemplars:
        logger.info("No active exemplars found for platform=%s", platform)
        return []

    matching = [e for e in all_exemplars if e.vertical == vertical]
    others = [e for e in all_exemplars if e.vertical != vertical]

    if len(matching) >= _MIN_EXEMPLARS:
        count = random.randint(_MIN_EXEMPLARS, min(_MAX_EXEMPLARS, len(matching)))
        selected = random.sample(matching, count)
    else:
        selected = list(matching)
        remaining = _MIN_EXEMPLARS - len(selected)
        if others and remaining > 0:
            fill_count = min(remaining, len(others))
            selected.extend(random.sample(others, fill_count))

    logger.info(
        "Selected %d exemplars (vertical=%s, matched=%d, filled=%d)",
        len(selected), vertical, len(matching), max(0, len(selected) - len(matching)),
    )
    return selected
