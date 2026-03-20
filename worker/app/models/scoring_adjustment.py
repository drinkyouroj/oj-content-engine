"""
ScoringAdjustment model — per-keyword scoring tweaks from Justin.

Implements PRD Section 3 (Scoring Adjustments).
Maps to the `scoring_adjustments` table in Postgres.

Justin creates adjustments from the review UI to fine-tune how specific
keywords/topics are scored. Adjustments range from -20 to +20 and are
applied during Pass 1 of scoring.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from worker.app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ScoringAdjustment(UUIDPrimaryKey, TimestampMixin, Base):
    """Per-keyword scoring adjustment created by Justin from the review UI.

    Attributes:
        keyword: Keyword or topic string to match against signals.
        dimension: Which scoring dimension to adjust (e.g. 'signal_strength').
        adjustment: Integer adjustment value, constrained to -20..+20.
        created_by: Who created this adjustment.
    """

    __tablename__ = "scoring_adjustments"
    __table_args__ = (
        CheckConstraint("adjustment >= -20 AND adjustment <= 20", name="ck_adjustment_range"),
    )

    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[str] = mapped_column(Text, nullable=False)
    adjustment: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
