"""
VoiceExemplar model — curated brand voice reference posts.

Implements PRD Section 4 (Voice Injection Points).
Maps to the `voice_exemplars` table in Postgres.

10-15 posts curated by Justin. 3-5 randomly selected per generation run.
Managed via /dashboard/settings/exemplars. Refreshed quarterly.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Enum, Text
from sqlalchemy.orm import Mapped, mapped_column

from worker.app.models.base import Base, TimestampMixin, UUIDPrimaryKey
from worker.app.models.content_draft import Platform


class VoiceExemplar(UUIDPrimaryKey, TimestampMixin, Base):
    """Brand voice reference post for content generation.

    Attributes:
        content: Full text of the exemplar post.
        platform: Which platform this exemplar is for.
        active: Whether this exemplar is currently in use.
    """

    __tablename__ = "voice_exemplars"

    content: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, name="platform", native_enum=True, create_type=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    vertical: Mapped[str] = mapped_column(Text, default="general", server_default="general", nullable=False)
