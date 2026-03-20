"""
Signal model — raw discovered trends from all sources.

Implements PRD Section 2 (Trend Discovery Layer).
Maps to the `signals` table in Postgres.

Each signal represents a single URL discovered by a poller (RSS, Reddit,
HN, or Twitter). Deduplication is enforced via a SHA-256 hash of the
normalized URL.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from worker.app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class SignalSource(str, enum.Enum):
    """Allowed signal sources per PRD Section 2."""

    RSS = "rss"
    REDDIT = "reddit"
    HN = "hn"
    TWITTER = "twitter"


class Signal(UUIDPrimaryKey, TimestampMixin, Base):
    """Raw discovered trend from a polling source.

    Attributes:
        source: Which poller discovered this signal.
        url: Original URL of the trend.
        title: Signal title.
        body_preview: First 500 characters of the content.
        discovered_at: Timestamp when the poller found it.
        source_metrics: JSONB with upvotes, comments, shares, velocity.
        dedup_hash: SHA-256 of normalized URL for deduplication.
    """

    __tablename__ = "signals"

    source: Mapped[SignalSource] = mapped_column(
        Enum(SignalSource, name="signal_source", native_enum=True),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dedup_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    # Relationships
    scored_signals: Mapped[list["ScoredSignal"]] = relationship(
        back_populates="signal", cascade="all, delete-orphan"
    )
