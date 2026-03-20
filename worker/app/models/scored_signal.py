"""
ScoredSignal model — signals after two-pass scoring.

Implements PRD Section 3 (Topic Triage Rubric).
Maps to the `scored_signals` table in Postgres.

Pass 1 is rule-based (zero LLM cost). Pass 2 uses Claude Haiku for
subjective dimensions. The score_breakdown JSONB contains all 6 dimensions:
signal_strength, timing_window, depth_potential, novelty,
community_resonance, brand_angle_availability.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from worker.app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ScoringStatus(str, enum.Enum):
    """Scoring pipeline status."""

    PENDING = "pending"
    SCORED = "scored"
    FAILED = "failed"


class ScoredSignal(UUIDPrimaryKey, TimestampMixin, Base):
    """Signal with scoring results from the two-pass rubric.

    Attributes:
        signal_id: FK to the original signal.
        score_breakdown: JSONB with all 6 scoring dimensions (0-100 each).
        composite_score: Weighted composite score (0-100).
        status: Current scoring status.
        pass1_completed_at: When rule-based scoring finished.
        pass2_completed_at: When LLM scoring finished.
    """

    __tablename__ = "scored_signals"

    signal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    composite_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[ScoringStatus] = mapped_column(
        Enum(ScoringStatus, name="scoring_status", native_enum=True),
        nullable=False,
        default=ScoringStatus.PENDING,
        server_default="pending",
    )
    pass1_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pass2_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    signal: Mapped["Signal"] = relationship(back_populates="scored_signals")
    topics: Mapped[list["Topic"]] = relationship(
        back_populates="scored_signal", cascade="all, delete-orphan"
    )
