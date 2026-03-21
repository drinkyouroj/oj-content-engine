"""
Dead source detection for the trend discovery layer.

Implements PRD Section 2 (Fallback Behavior). Tracks consecutive zero-result
poller runs in the system_alerts table. After 3 consecutive failures, an
alert is created or updated. When a poller recovers (returns results),
any active alert is resolved.

Inputs: Poller result count after each run.
Outputs: SystemAlert rows created, updated, or resolved in the database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.system_alert import SystemAlert

logger = logging.getLogger(__name__)

#: Alert type used for dead source detection
ALERT_TYPE = "consecutive_failures"

#: Threshold of consecutive zero-result runs before alerting
FAILURE_THRESHOLD = 3


async def update_alert(session: AsyncSession, source: str, result_count: int) -> None:
    """Update dead source detection state after a poller run.

    Called at the end of every BasePoller.run(). Logic:
    - result_count == 0: increment consecutive_failures. If >= FAILURE_THRESHOLD,
      create or update an alert.
    - result_count > 0: resolve any active alert for this source.

    Args:
        session: Async SQLAlchemy session for database operations.
        source: Poller source identifier (e.g. 'rss', 'reddit', 'hn', 'twitter').
        result_count: Number of new signals inserted in this run.
    """
    now = datetime.now(tz=timezone.utc)

    # Find the active (unresolved) alert for this source, if any
    stmt = select(SystemAlert).where(
        SystemAlert.source == source,
        SystemAlert.alert_type == ALERT_TYPE,
        SystemAlert.resolved_at.is_(None),
    )
    result = await session.execute(stmt)
    alert = result.scalar_one_or_none()

    if result_count > 0:
        # Poller recovered — resolve any active alert
        if alert is not None:
            alert.resolved_at = now
            alert.consecutive_failures = 0
            await session.commit()
            logger.info("Resolved dead source alert for %s", source)
        return

    # result_count == 0 — increment failure tracking
    if alert is not None:
        alert.consecutive_failures += 1
        alert.last_failure_at = now
        await session.commit()
        logger.warning(
            "Dead source alert for %s: %d consecutive failures",
            source,
            alert.consecutive_failures,
        )
    else:
        # No active alert yet — check if we need to create one
        # We track from 1 because this is the first failure we're seeing
        # We only create the alert row once we hit the threshold
        # But we need somewhere to track sub-threshold failures.
        # Strategy: always create the alert row, but only log a warning
        # when threshold is reached.
        new_alert = SystemAlert(
            source=source,
            alert_type=ALERT_TYPE,
            consecutive_failures=1,
            last_failure_at=now,
        )
        session.add(new_alert)
        await session.commit()

        if new_alert.consecutive_failures >= FAILURE_THRESHOLD:
            logger.warning(
                "New dead source alert for %s: %d consecutive failures",
                source,
                new_alert.consecutive_failures,
            )
        else:
            logger.info(
                "Tracking failure for %s: %d consecutive failures",
                source,
                new_alert.consecutive_failures,
            )
