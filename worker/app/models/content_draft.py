"""
ContentDraft model — per-platform generated content.

Implements PRD Sections 4 (Content Generation Pipeline) and 5 (Per-Platform Output Specs).
Maps to the `content_drafts` table in Postgres.

Each topic produces up to 4 drafts (one per platform). Each draft is an
independent ARQ task. Partial success is acceptable.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from worker.app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Platform(str, enum.Enum):
    """Target content platforms per PRD Section 5."""

    SUBSTACK = "substack"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"


class DraftStatus(str, enum.Enum):
    """Draft lifecycle status per PRD Section 6."""

    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    KILLED = "killed"


class ContentDraft(UUIDPrimaryKey, TimestampMixin, Base):
    """Platform-specific content draft generated from a topic.

    Attributes:
        topic_id: FK to the parent topic.
        platform: Target platform (substack, twitter, linkedin, instagram).
        content: Generated draft body text.
        status: Draft lifecycle status.
        notion_page_id: Notion page URL/ID once staged.
        model_used: LLM model identifier (e.g. claude-sonnet-4-5).
        token_cost: Approximate generation cost in USD.
        image_url: Instagram image card URL (Vercel Blob).
        generated_at: When the draft was generated.
    """

    __tablename__ = "content_drafts"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, name="platform", native_enum=True, values_callable=lambda e: [m.value for m in e]), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, name="draft_status", native_enum=True, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=DraftStatus.DRAFT,
        server_default="draft",
    )
    notion_page_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_cost: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    topic: Mapped["Topic"] = relationship(back_populates="content_drafts")
