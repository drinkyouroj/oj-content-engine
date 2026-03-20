"""
Topic model — triaged topics awaiting thesis injection and/or generation.

Implements PRD Section 3 (Triage) and 3.5 (Thesis Injection).
Maps to the `topics` table in Postgres.

Topics are created after triage. Status flow:
queued (>=65) or review (55-64) -> generating -> generated -> archived/killed
Optional thesis injection at any point before generation.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from worker.app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class TopicStatus(str, enum.Enum):
    """Topic lifecycle status per PRD Sections 3 and 3.5."""

    QUEUED = "queued"
    REVIEW = "review"
    GENERATING = "generating"
    GENERATED = "generated"
    SNOOZED = "snoozed"
    ARCHIVED = "archived"
    KILLED = "killed"


class Topic(UUIDPrimaryKey, TimestampMixin, Base):
    """Triaged topic with optional thesis injection.

    Attributes:
        scored_signal_id: FK to the scored signal this topic originated from.
        status: Current topic lifecycle status.
        thesis: Justin's 2-3 sentence take (nullable — may skip).
        thesis_provided: Whether a thesis was provided before generation.
        queued_at: When the topic was queued for generation.
        reviewed_by: Who reviewed the topic (always Justin for now).
        review_decision: Decision notes from manual review.
    """

    __tablename__ = "topics"

    scored_signal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scored_signals.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus, name="topic_status", native_enum=True, values_callable=lambda e: [m.value for m in e]), nullable=False
    )
    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    thesis_provided: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_decision: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    scored_signal: Mapped["ScoredSignal"] = relationship(back_populates="topics")
    content_drafts: Mapped[list["ContentDraft"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
