"""
SystemAlert model — poller health monitoring.

Implements PRD Section 2 (Fallback Behavior).
Maps to the `system_alerts` table in Postgres.

Dead source detection: 3 consecutive runs returning 0 results triggers
an alert. Alerts surface in the Vercel UI health dashboard.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from worker.app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class SystemAlert(UUIDPrimaryKey, TimestampMixin, Base):
    """Poller health alert for dead source detection.

    Attributes:
        source: Which poller raised the alert.
        alert_type: Type of alert (e.g. 'consecutive_failures').
        consecutive_failures: Number of consecutive zero-result runs.
        last_failure_at: When the most recent failure occurred.
        resolved_at: When the alert was resolved (null if active).
    """

    __tablename__ = "system_alerts"

    source: Mapped[str] = mapped_column(Text, nullable=False)
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
