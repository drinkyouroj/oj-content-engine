# Infrastructure Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up the Worker layer foundation — Postgres schema (7 tables), FastAPI app, ARQ task queue, Docker container, and Alembic migrations.

**Architecture:** Two-layer split (Vercel + Worker). This plan builds the Worker layer only. All 7 SQLAlchemy models map to PRD tables, served by a FastAPI app with an ARQ background worker, containerized for Railway deployment.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x (async), asyncpg, Alembic, ARQ, pydantic-settings, Docker

**Spec:** `docs/superpowers/specs/2026-03-19-infra-scaffold-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `worker/pyproject.toml` | Create | Project metadata, deps, pytest config |
| `worker/app/__init__.py` | Create | Empty package init |
| `worker/app/config.py` | Create | pydantic-settings Settings class |
| `worker/app/models/__init__.py` | Create | Re-exports all models |
| `worker/app/models/base.py` | Create | DeclarativeBase + TimestampMixin |
| `worker/app/models/signal.py` | Create | Signal model |
| `worker/app/models/scored_signal.py` | Create | ScoredSignal model |
| `worker/app/models/topic.py` | Create | Topic model |
| `worker/app/models/content_draft.py` | Create | ContentDraft model |
| `worker/app/models/voice_exemplar.py` | Create | VoiceExemplar model |
| `worker/app/models/scoring_adjustment.py` | Create | ScoringAdjustment model |
| `worker/app/models/system_alert.py` | Create | SystemAlert model |
| `worker/app/models/test_models.py` | Create | Model unit tests |
| `worker/app/database.py` | Create | Async engine + session factory |
| `worker/app/main.py` | Create | FastAPI app + /health endpoint |
| `worker/app/test_main.py` | Create | Health endpoint tests |
| `worker/app/README.md` | Create | App module overview |
| `worker/jobs/__init__.py` | Create | Empty package init |
| `worker/jobs/worker.py` | Create | ARQ WorkerSettings + ping job |
| `worker/jobs/test_worker.py` | Create | Worker job tests |
| `worker/jobs/README.md` | Create | Jobs module overview |
| `worker/alembic.ini` | Create | Alembic config |
| `worker/alembic/env.py` | Create | Async Alembic env |
| `worker/alembic/script.py.mako` | Create | Migration template |
| `worker/alembic/versions/001_initial_schema.py` | Create | Initial migration (7 tables) |
| `worker/conftest.py` | Create | Shared pytest fixtures |
| `worker/Dockerfile` | Create | Multi-stage Railway build |
| `worker/docker-compose.yml` | Create | Worker service only |
| `worker/entrypoint.sh` | Create | uvicorn + ARQ launcher |
| `worker/README.md` | Create | Worker overview |
| `docs/decisions/003-sqlalchemy-orm.md` | Create | Decision doc |
| `docs/decisions/004-no-local-dev-containers.md` | Create | Decision doc |
| `CHANGELOG.md` | Modify | Add infra scaffold entries |

---

## Task 1: Project Skeleton + pyproject.toml

**Files:**
- Create: `worker/pyproject.toml`
- Create: `worker/app/__init__.py`
- Create: `worker/app/models/__init__.py` (empty initially)
- Create: `worker/jobs/__init__.py`

- [ ] **Step 1: Create worker directory and pyproject.toml**

```toml
[project]
name = "oj-content-engine-worker"
version = "0.1.0"
description = "Worker layer for the OJ Content Engine pipeline"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "arq>=0.26.1",
    "pydantic-settings>=2.7.0",
    "httpx>=0.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.25.0",
    "ruff>=0.8.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["app", "jobs"]

[tool.ruff]
target-version = "py312"
line-length = 100
```

- [ ] **Step 2: Create empty __init__.py files**

```python
# worker/app/__init__.py — empty
# worker/app/models/__init__.py — empty (populated in Task 3)
# worker/jobs/__init__.py — empty
```

- [ ] **Step 3: Verify structure**

Run: `ls -R worker/`
Expected: `pyproject.toml`, `app/__init__.py`, `app/models/__init__.py`, `jobs/__init__.py`

- [ ] **Step 4: Commit**

```bash
git add worker/pyproject.toml worker/app/__init__.py worker/app/models/__init__.py worker/jobs/__init__.py
git commit -m "chore(worker): add pyproject.toml and package skeleton"
```

---

## Task 2: Config + Database Foundation

**Files:**
- Create: `worker/app/config.py`
- Create: `worker/app/database.py`

- [ ] **Step 1: Create config.py**

```python
"""
Application configuration via environment variables.

Reads from .env file or environment. Required vars fail fast on startup.
Implements PRD Section 8 (Tech Stack Decisions).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Worker application settings. Required vars have no default and will
    raise ValidationError if missing from the environment."""

    # Required — Worker cannot start without these
    database_url: str
    arq_redis_url: str
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str

    # Optional — not needed for scaffold, required by future feature branches
    anthropic_api_key: str = ""
    notion_api_key: str = ""
    notion_db_id: str = ""
    worker_secret: str = ""

    # RSS/social sources — populated by feature/discovery
    rss_feed_urls: str = ""
    twitter_bearer_token: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def get_settings() -> Settings:
    """Instantiate and return application settings.

    Returns:
        Settings loaded from environment variables.

    Raises:
        pydantic.ValidationError: If required env vars are missing.
    """
    return Settings()
```

- [ ] **Step 2: Create database.py**

```python
"""
Async SQLAlchemy engine and session factory.

Provides the database connection pool shared by FastAPI request handlers
and ARQ background jobs. Connects to Neon Postgres via asyncpg.
Implements PRD Section 8 (Shared Infrastructure).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from worker.app.config import get_settings


def make_engine():
    """Create an async SQLAlchemy engine from DATABASE_URL.

    Connection pool: 5 min, 20 max connections. The URL is rewritten
    from postgresql:// to postgresql+asyncpg:// for the asyncpg driver.

    Returns:
        AsyncEngine configured for Neon Postgres.
    """
    settings = get_settings()
    url = settings.database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(url, pool_size=5, max_overflow=15, echo=False)


def make_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the given engine.

    Args:
        engine: AsyncEngine to bind sessions to.

    Returns:
        async_sessionmaker producing AsyncSession instances.
    """
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

- [ ] **Step 3: Commit**

```bash
git add worker/app/config.py worker/app/database.py
git commit -m "feat(worker): add config and async database foundation"
```

---

## Task 3: Base Model + Timestamp Mixin

**Files:**
- Create: `worker/app/models/base.py`

- [ ] **Step 1: Create base.py with DeclarativeBase and TimestampMixin**

```python
"""
SQLAlchemy base class and shared mixins for all models.

All models inherit from Base and use TimestampMixin for created_at/updated_at.
UUIDs for all primary keys per spec.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


class TimestampMixin:
    """Mixin adding created_at and updated_at columns to any model.

    created_at is set on INSERT. updated_at is set on INSERT and UPDATE.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKey:
    """Mixin adding a UUID primary key column."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
```

- [ ] **Step 2: Commit**

```bash
git add worker/app/models/base.py
git commit -m "feat(db): add SQLAlchemy base class with UUID PK and timestamp mixins"
```

---

## Task 4: Signal Model

**Files:**
- Create: `worker/app/models/signal.py`

- [ ] **Step 1: Create signal.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add worker/app/models/signal.py
git commit -m "feat(db): add Signal model for trend discovery"
```

---

## Task 5: ScoredSignal Model

**Files:**
- Create: `worker/app/models/scored_signal.py`

- [ ] **Step 1: Create scored_signal.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add worker/app/models/scored_signal.py
git commit -m "feat(db): add ScoredSignal model for two-pass scoring"
```

---

## Task 6: Topic Model

**Files:**
- Create: `worker/app/models/topic.py`

- [ ] **Step 1: Create topic.py**

```python
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
        Enum(TopicStatus, name="topic_status", native_enum=True), nullable=False
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
```

- [ ] **Step 2: Commit**

```bash
git add worker/app/models/topic.py
git commit -m "feat(db): add Topic model for triage and thesis injection"
```

---

## Task 7: ContentDraft Model

**Files:**
- Create: `worker/app/models/content_draft.py`

- [ ] **Step 1: Create content_draft.py**

```python
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
        Enum(Platform, name="platform", native_enum=True), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, name="draft_status", native_enum=True),
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
```

- [ ] **Step 2: Commit**

```bash
git add worker/app/models/content_draft.py
git commit -m "feat(db): add ContentDraft model for per-platform generation"
```

---

## Task 8: Remaining Models (VoiceExemplar, ScoringAdjustment, SystemAlert)

**Files:**
- Create: `worker/app/models/voice_exemplar.py`
- Create: `worker/app/models/scoring_adjustment.py`
- Create: `worker/app/models/system_alert.py`

- [ ] **Step 1: Create voice_exemplar.py**

```python
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
        Enum(Platform, name="platform", native_enum=True, create_type=False),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
```

- [ ] **Step 2: Create scoring_adjustment.py**

```python
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
```

- [ ] **Step 3: Create system_alert.py**

```python
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
```

- [ ] **Step 4: Update models/__init__.py to re-export all models**

```python
"""
ORM model re-exports.

Import all models here so that Alembic's autogenerate and any module
that does `from worker.app.models import *` picks up every table.
"""

from worker.app.models.base import Base, TimestampMixin, UUIDPrimaryKey
from worker.app.models.content_draft import ContentDraft, DraftStatus, Platform
from worker.app.models.scored_signal import ScoredSignal, ScoringStatus
from worker.app.models.scoring_adjustment import ScoringAdjustment
from worker.app.models.signal import Signal, SignalSource
from worker.app.models.system_alert import SystemAlert
from worker.app.models.topic import Topic, TopicStatus
from worker.app.models.voice_exemplar import VoiceExemplar

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKey",
    "ContentDraft",
    "DraftStatus",
    "Platform",
    "ScoredSignal",
    "ScoringStatus",
    "ScoringAdjustment",
    "Signal",
    "SignalSource",
    "SystemAlert",
    "Topic",
    "TopicStatus",
    "VoiceExemplar",
]
```

- [ ] **Step 5: Commit**

```bash
git add worker/app/models/
git commit -m "feat(db): add VoiceExemplar, ScoringAdjustment, SystemAlert models and re-exports"
```

---

## Task 9: Model Unit Tests

**Files:**
- Create: `worker/app/models/test_models.py`

- [ ] **Step 1: Write model tests**

```python
"""
Unit tests for SQLAlchemy models.

Validates model instantiation, enum values, timestamp mixin presence,
and table names. Does NOT require a database connection — tests model
definitions only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from worker.app.models import (
    Base,
    ContentDraft,
    DraftStatus,
    Platform,
    ScoredSignal,
    ScoringAdjustment,
    ScoringStatus,
    Signal,
    SignalSource,
    SystemAlert,
    Topic,
    TopicStatus,
    VoiceExemplar,
)


class TestEnumValues:
    """Verify enum members match PRD specifications."""

    def test_signal_source_values(self):
        assert set(s.value for s in SignalSource) == {"rss", "reddit", "hn", "twitter"}

    def test_scoring_status_values(self):
        assert set(s.value for s in ScoringStatus) == {"pending", "scored", "failed"}

    def test_topic_status_values(self):
        expected = {"queued", "review", "generating", "generated", "snoozed", "archived", "killed"}
        assert set(s.value for s in TopicStatus) == expected

    def test_platform_values(self):
        assert set(p.value for p in Platform) == {"substack", "twitter", "linkedin", "instagram"}

    def test_draft_status_values(self):
        assert set(s.value for s in DraftStatus) == {"draft", "review", "approved", "published", "killed"}


class TestTableNames:
    """Verify __tablename__ matches expected database table names."""

    def test_signal_table(self):
        assert Signal.__tablename__ == "signals"

    def test_scored_signal_table(self):
        assert ScoredSignal.__tablename__ == "scored_signals"

    def test_topic_table(self):
        assert Topic.__tablename__ == "topics"

    def test_content_draft_table(self):
        assert ContentDraft.__tablename__ == "content_drafts"

    def test_voice_exemplar_table(self):
        assert VoiceExemplar.__tablename__ == "voice_exemplars"

    def test_scoring_adjustment_table(self):
        assert ScoringAdjustment.__tablename__ == "scoring_adjustments"

    def test_system_alert_table(self):
        assert SystemAlert.__tablename__ == "system_alerts"


class TestTimestampMixin:
    """Verify all models have created_at and updated_at columns."""

    @pytest.mark.parametrize("model", [
        Signal, ScoredSignal, Topic, ContentDraft,
        VoiceExemplar, ScoringAdjustment, SystemAlert,
    ])
    def test_has_timestamp_columns(self, model):
        columns = {c.name for c in model.__table__.columns}
        assert "created_at" in columns
        assert "updated_at" in columns


class TestUUIDPrimaryKey:
    """Verify all models use UUID primary keys."""

    @pytest.mark.parametrize("model", [
        Signal, ScoredSignal, Topic, ContentDraft,
        VoiceExemplar, ScoringAdjustment, SystemAlert,
    ])
    def test_has_uuid_pk(self, model):
        pk_cols = [c for c in model.__table__.columns if c.primary_key]
        assert len(pk_cols) == 1
        assert pk_cols[0].name == "id"


class TestModelInstantiation:
    """Verify models can be instantiated with required fields."""

    def test_signal_instantiation(self):
        s = Signal(
            source=SignalSource.RSS,
            url="https://example.com",
            title="Test Signal",
            discovered_at=datetime.now(timezone.utc),
            dedup_hash="abc123",
        )
        assert s.source == SignalSource.RSS
        assert s.url == "https://example.com"

    def test_scored_signal_instantiation(self):
        ss = ScoredSignal(
            signal_id=uuid.uuid4(),
            score_breakdown={
                "signal_strength": 70,
                "timing_window": 50,
                "depth_potential": 80,
                "novelty": 60,
                "community_resonance": 40,
                "brand_angle_availability": 85,
            },
            composite_score=64.5,
        )
        assert ss.composite_score == 64.5
        assert len(ss.score_breakdown) == 6

    def test_scoring_adjustment_range_constraint_exists(self):
        """Verify the CHECK constraint for adjustment range is defined."""
        constraints = [
            c.name for c in ScoringAdjustment.__table__.constraints
            if hasattr(c, "name") and c.name
        ]
        assert "ck_adjustment_range" in constraints
```

- [ ] **Step 2: Install deps and run tests**

Run (from `worker/` directory):
```bash
pip install -e ".[dev]"
pytest app/models/test_models.py -v
```
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add worker/app/models/test_models.py
git commit -m "test(db): add model unit tests for enums, table names, and constraints"
```

---

## Task 10: Alembic Setup + Initial Migration

**Files:**
- Create: `worker/alembic.ini`
- Create: `worker/alembic/env.py`
- Create: `worker/alembic/script.py.mako`
- Create: `worker/alembic/versions/` (directory)

- [ ] **Step 1: Create alembic.ini**

```ini
[alembic]
script_location = alembic
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Create alembic/env.py (async)**

```python
"""
Alembic environment configuration for async SQLAlchemy.

Uses asyncpg driver via run_async_migrations(). Reads DATABASE_URL
from the application config rather than alembic.ini.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from worker.app.config import get_settings
from worker.app.models import Base  # noqa: F401 — ensures all models are registered

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    """Get the database URL from app config, rewritten for asyncpg."""
    url = get_settings().database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without connecting."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Execute migrations against a live connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations."""
    engine = create_async_engine(_get_url())
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the database."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Create alembic/script.py.mako**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Create versions directory**

```bash
mkdir -p worker/alembic/versions
```

- [ ] **Step 5: Commit**

```bash
git add worker/alembic.ini worker/alembic/
git commit -m "chore(db): add Alembic async configuration"
```

---

## Task 11: Generate Initial Migration

This task requires a running Postgres instance (Neon) to autogenerate.

- [ ] **Step 1: Generate migration from models**

Run (from `worker/` directory):
```bash
cd worker && alembic revision --autogenerate -m "initial schema — 7 tables"
```
Expected: Creates `alembic/versions/<hash>_initial_schema_7_tables.py` with
all 7 tables, enums, constraints, and indexes.

- [ ] **Step 2: Review the generated migration**

Open the generated file and verify:
- All 7 tables present: signals, scored_signals, topics, content_drafts, voice_exemplars, scoring_adjustments, system_alerts
- All enums created: signal_source, scoring_status, topic_status, platform, draft_status
- Foreign keys: scored_signals.signal_id → signals.id, topics.scored_signal_id → scored_signals.id, content_drafts.topic_id → topics.id
- Check constraint: ck_adjustment_range on scoring_adjustments
- Unique constraint: signals.dedup_hash
- Downgrade drops all tables and enums

- [ ] **Step 3: Rename the file to use a sequential prefix**

```bash
# Rename the generated file to use a clean sequential prefix
mv worker/alembic/versions/*_initial_schema*.py worker/alembic/versions/001_initial_schema.py
```

Note: Keep the `revision` and `down_revision` fields inside the file intact — Alembic uses those for ordering, not filenames. The rename is purely for human readability.

- [ ] **Step 4: Run the migration**

```bash
cd worker && alembic upgrade head
```
Expected: `INFO [alembic.runtime.migration] Running upgrade -> <revision>, initial schema — 7 tables`

- [ ] **Step 5: Commit**

```bash
git add worker/alembic/versions/
git commit -m "feat(db): add initial migration with all 7 PRD tables"
```

---

## Task 12: FastAPI App + Health Endpoint

**Files:**
- Create: `worker/app/main.py`
- Create: `worker/app/test_main.py`

- [ ] **Step 1: Write the health endpoint test**

```python
"""
Tests for the FastAPI application and /health endpoint.

Uses mocked database and Redis connections to test without external deps.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from worker.app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_healthy():
    """Health endpoint returns 200 with status 'healthy' when all services are up."""
    with (
        patch("worker.app.main.check_db", new_callable=AsyncMock, return_value=True),
        patch("worker.app.main.check_redis", new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] is True
        assert data["redis"] is True


@pytest.mark.asyncio
async def test_health_endpoint_db_down():
    """Health endpoint returns 503 when database is unreachable."""
    with (
        patch("worker.app.main.check_db", new_callable=AsyncMock, return_value=False),
        patch("worker.app.main.check_redis", new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker && pytest app/test_main.py -v`
Expected: FAIL — `worker.app.main` does not exist yet

- [ ] **Step 3: Implement main.py**

```python
"""
FastAPI application for the OJ Content Engine worker.

Provides a /health endpoint for Railway health checks. The application
lifecycle manages database and Redis connections.

Implements PRD Section 8 (Worker Layer).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory

logger = logging.getLogger(__name__)

# Module-level state populated during lifespan
_engine = None
_session_factory = None
_redis_settings = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database engine and Redis connection pool lifecycle.

    Creates connections on startup, closes them on shutdown.
    """
    global _engine, _session_factory, _redis_settings

    settings = get_settings()
    _engine = make_engine()
    _session_factory = make_session_factory(_engine)
    _redis_settings = RedisSettings.from_dsn(settings.arq_redis_url)

    logger.info("Worker started — database and Redis connections ready")
    yield

    await _engine.dispose()
    _engine = None
    _session_factory = None
    _redis_settings = None
    logger.info("Worker stopped — connections closed")


app = FastAPI(
    title="OJ Content Engine Worker",
    version="0.1.0",
    lifespan=lifespan,
)


async def check_db() -> bool:
    """Check database connectivity by executing a simple query.

    Returns:
        True if the database is reachable, False otherwise.
    """
    if _session_factory is None:
        return False
    try:
        async with _session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database health check failed")
        return False


async def check_redis() -> bool:
    """Check Redis connectivity by creating a pool and pinging.

    Returns:
        True if Redis is reachable, False otherwise.
    """
    if _redis_settings is None:
        return False
    try:
        pool = await create_pool(_redis_settings)
        await pool.ping()
        await pool.close()
        return True
    except Exception:
        logger.exception("Redis health check failed")
        return False


@app.get("/health")
async def health():
    """Health check endpoint for Railway.

    Returns:
        JSON with status, database, and redis connectivity.
        200 if all healthy, 503 if any service is down.
    """
    db_ok = await check_db()
    redis_ok = await check_redis()
    healthy = db_ok and redis_ok

    body = {"status": "healthy" if healthy else "unhealthy", "database": db_ok, "redis": redis_ok}
    return JSONResponse(content=body, status_code=200 if healthy else 503)
```

- [ ] **Step 4: Run tests**

Run: `cd worker && pytest app/test_main.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add worker/app/main.py worker/app/test_main.py
git commit -m "feat(worker): add FastAPI app with /health endpoint"
```

---

## Task 13: ARQ Worker + Ping Job

**Files:**
- Create: `worker/jobs/worker.py`
- Create: `worker/jobs/test_worker.py`

- [ ] **Step 1: Write the worker test**

```python
"""
Tests for the ARQ worker configuration and example ping job.
"""

from __future__ import annotations

import pytest

from worker.jobs.worker import WorkerSettings, ping


@pytest.mark.asyncio
async def test_ping_job():
    """Ping job returns the expected pong message."""
    result = await ping({})
    assert result == "pong"


def test_worker_settings_has_functions():
    """WorkerSettings registers at least the ping function."""
    func_names = [f.__name__ if callable(f) else f for f in WorkerSettings.functions]
    assert "ping" in func_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker && pytest jobs/test_worker.py -v`
Expected: FAIL — `worker.jobs.worker` does not exist yet

- [ ] **Step 3: Implement worker.py**

```python
"""
ARQ worker configuration and job registry.

Connects to Upstash Redis via ARQ_REDIS_URL. Future feature branches
register their cron functions and jobs here.

Implements PRD Section 8 (ARQ as async task queue).
"""

from __future__ import annotations

import logging

from arq.connections import RedisSettings

from worker.app.config import get_settings

logger = logging.getLogger(__name__)


async def ping(ctx: dict) -> str:
    """Example ARQ job that proves the worker is running.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        The string 'pong'.

    Estimated runtime: <1s
    Retry behavior: None (example job)
    Failure mode: Logs error, no downstream impact
    """
    logger.info("ping job executed")
    return "pong"


class WorkerSettings:
    """ARQ worker settings.

    Configures the Redis connection and registers available job functions.
    Future feature branches add their functions to the `functions` list
    and cron_jobs to `cron_jobs`.
    """

    functions = [ping]
    cron_jobs = []

    @staticmethod
    def redis_settings() -> RedisSettings:
        """Build Redis connection settings from app config.

        Returns:
            RedisSettings configured for Upstash Redis.
        """
        settings = get_settings()
        return RedisSettings.from_dsn(settings.arq_redis_url)
```

- [ ] **Step 4: Run tests**

Run: `cd worker && pytest jobs/test_worker.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add worker/jobs/worker.py worker/jobs/test_worker.py
git commit -m "feat(worker): add ARQ worker config with example ping job"
```

---

## Task 14: Docker + Entrypoint

**Files:**
- Create: `worker/Dockerfile`
- Create: `worker/docker-compose.yml`
- Create: `worker/entrypoint.sh`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Stage 1: Builder — install Python dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy source first so pip install can find the package
COPY pyproject.toml .
COPY app/ app/
COPY jobs/ jobs/

RUN pip install --no-cache-dir .

# Stage 2: Runtime — slim image with only what's needed
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages (site-packages) from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy application source
COPY . .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Railway injects PORT; default to 8000 for local dev
ENV PORT=8000
EXPOSE ${PORT}

ENTRYPOINT ["./entrypoint.sh"]
```

- [ ] **Step 2: Create entrypoint.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Starting OJ Content Engine Worker..."
echo "  FastAPI on port ${PORT:-8000}"
echo "  ARQ worker connecting to Redis"

# Run both processes; exit if either dies
uvicorn worker.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
python -m arq worker.jobs.worker.WorkerSettings &
wait -n
```

- [ ] **Step 3: Create docker-compose.yml**

Note: Run `docker compose up` from within `worker/` directory.

```yaml
services:
  worker:
    build:
      context: .
      dockerfile: Dockerfile
    env_file: ../.env  # .env lives at project root
    ports:
      - "8000:8000"
```

- [ ] **Step 4: Verify Docker build**

Run: `cd worker && docker build -t oj-worker .`
Expected: Build completes without errors

- [ ] **Step 5: Commit**

```bash
git add worker/Dockerfile worker/docker-compose.yml worker/entrypoint.sh
git commit -m "chore(worker): add Dockerfile, docker-compose, and entrypoint for Railway"
```

---

## Task 15: conftest.py + READMEs

**Files:**
- Create: `worker/conftest.py`
- Create: `worker/README.md`
- Create: `worker/app/README.md`
- Create: `worker/jobs/README.md`

- [ ] **Step 1: Create conftest.py**

```python
"""
Shared pytest fixtures for the worker test suite.

pytest-asyncio with asyncio_mode = "auto" in pyproject.toml handles
async test discovery automatically. Add shared fixtures here as the
test suite grows.
"""

from __future__ import annotations
```

- [ ] **Step 2: Create worker/README.md**

```markdown
# Worker Layer

## Purpose

The Worker layer runs long-running pipeline operations: trend discovery,
signal scoring, content generation, and Notion staging. Built with
FastAPI + ARQ on Docker, deployed to Railway. Implements PRD Sections 1-5.

## Structure

- `app/` — FastAPI application, config, database, ORM models
- `jobs/` — ARQ worker configuration and background job definitions
- `alembic/` — Database migration files

## How it fits in the pipeline

The Worker is the data processing engine. It polls external sources,
scores signals, generates content, and writes to Notion. It shares
Neon Postgres and Upstash Redis with the Vercel layer.

## Environment variables required

See `.env.example` in the project root. Required for Worker:
- `DATABASE_URL` — Neon Postgres connection string
- `ARQ_REDIS_URL` — Redis URL for ARQ task queue
- `UPSTASH_REDIS_REST_URL` — Upstash REST URL
- `UPSTASH_REDIS_REST_TOKEN` — Upstash REST token

## Running locally

```bash
# Install dependencies
cd worker && pip install -e ".[dev]"

# Run FastAPI dev server
uvicorn worker.app.main:app --reload --port 8000

# Run ARQ worker (separate terminal)
arq worker.jobs.worker.WorkerSettings

# Run tests
pytest

# Run with Docker
docker compose up --build
```

- [ ] **Step 3: Create worker/app/README.md**

```markdown
# App Module

## Purpose

Core application code for the Worker layer: FastAPI app, configuration,
database connection management, and ORM model definitions.

## Structure

- `main.py` — FastAPI app with /health endpoint and lifespan management
- `config.py` — pydantic-settings configuration from environment variables
- `database.py` — Async SQLAlchemy engine and session factory
- `models/` — One ORM model per file, shared base class with UUID PK + timestamps

## How it fits in the pipeline

Provides the foundational infrastructure that all pipeline stages build on.
Models define the shared Postgres schema. Config validates required env vars.
Database module manages connection pooling.
```

- [ ] **Step 4: Create worker/jobs/README.md**

```markdown
# Jobs Module

## Purpose

ARQ background job definitions and worker configuration. Each pipeline
stage registers its jobs here. Implements PRD Section 8 (ARQ as async
task queue).

## Structure

- `worker.py` — ARQ WorkerSettings class, job registry, Redis connection
- Future: one file per pipeline stage (discovery_jobs.py, scoring_jobs.py, etc.)

## How it fits in the pipeline

ARQ jobs are the execution units of the pipeline. Discovery pollers,
scoring passes, content generation, and Notion staging all run as
independent ARQ jobs with retry and scheduling support.

## Running locally

```bash
# Run the ARQ worker
arq worker.jobs.worker.WorkerSettings
```

- [ ] **Step 5: Commit**

```bash
git add worker/conftest.py worker/README.md worker/app/README.md worker/jobs/README.md
git commit -m "docs(worker): add conftest.py and READMEs for worker, app, and jobs"
```

---

## Task 16: Decision Docs + CHANGELOG

**Files:**
- Create: `docs/decisions/003-sqlalchemy-orm.md`
- Create: `docs/decisions/004-no-local-dev-containers.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Create decision 003**

```markdown
# 003 — SQLAlchemy ORM Over Raw SQL
_Date: 2026-03-19 | Status: Accepted_

## Context

The Worker layer needs to interact with 7 Postgres tables. We need to
decide between raw SQL (via asyncpg directly), SQLAlchemy Core (table
definitions without ORM), or full SQLAlchemy ORM.

## Options Considered

1. **Raw asyncpg** — Write SQL strings directly, no abstraction layer.
   - Pros: Maximum performance, no ORM overhead, full SQL control
   - Cons: No Alembic autogenerate (must write migrations by hand).
     No relationship loading. Manual result-to-object mapping everywhere.

2. **SQLAlchemy Core** — Table definitions for Alembic, raw SQL for queries.
   - Pros: Alembic autogenerate works. Still close to SQL.
   - Cons: Awkward middle ground — defining tables twice (once for Alembic,
     once as query patterns). No relationship loading.

3. **SQLAlchemy ORM (async)** — Full ORM with mapped classes.
   - Pros: Alembic autogenerate. Pythonic queries. Relationship loading.
     Handles JSONB well. Type annotations via Mapped[].
   - Cons: ORM overhead (negligible at our scale). Learning curve for
     async patterns (mitigated by SQLAlchemy 2.x maturity).

## Decision

Option 3: Full async SQLAlchemy ORM. Alembic autogenerate is the killer
feature — writing 7 tables worth of migration SQL by hand is error-prone.
The ORM's relationship loading simplifies pipeline queries (e.g., loading
a topic with its scored signal and drafts). Performance overhead is
irrelevant at ~50 signals/day.

## Consequences

- **Easier:** Alembic autogenerate catches schema drift. Relationship
  loading simplifies multi-table queries in scoring and generation.
- **Harder:** Must understand SQLAlchemy async patterns (async sessions,
  lazy loading caveats). Team members need ORM familiarity.
- **Deferred:** If query performance becomes an issue (unlikely at scale),
  can drop to Core or raw SQL for hot paths without changing the models.
```

- [ ] **Step 2: Create decision 004**

```markdown
# 004 — No Local Dev Containers for Postgres/Redis
_Date: 2026-03-19 | Status: Accepted_

## Context

For local development, should docker-compose include local Postgres and
Redis containers, or should developers connect to the external Neon and
Upstash services?

## Options Considered

1. **Local containers** — docker-compose includes Postgres + Redis.
   - Pros: Fully offline development. No cloud costs during dev.
     Fast iteration (no network latency to cloud).
   - Cons: Schema drift risk (local Postgres may diverge from Neon).
     Need to seed data. Extra containers to manage. Doesn't test
     real connection behavior (Neon's serverless driver, Upstash REST).

2. **External only** — docker-compose runs Worker only, connects to Neon + Upstash.
   - Pros: Dev environment matches production exactly. No schema drift.
     Neon free tier is generous. Upstash free tier handles dev load.
     Tests real network behavior.
   - Cons: Requires internet. Cloud services must be provisioned.
     Slightly slower queries (network latency).

## Decision

Option 2: External only. Justin prefers developing against real services.
Neon's free tier provides branching (can create a dev branch), and Upstash's
free tier handles the minimal dev load. This eliminates an entire class of
"works locally but breaks in production" bugs.

## Consequences

- **Easier:** One fewer thing to configure. Dev behavior matches prod.
  Neon branching provides isolated dev databases without containers.
- **Harder:** Must have internet to develop. Need to provision Neon +
  Upstash before first dev session.
- **Deferred:** Can add local containers later if offline dev becomes
  necessary (e.g., travel, unreliable internet).
```

- [ ] **Step 3: Update CHANGELOG.md**

Add under `[Unreleased] / Added`:
```
- Worker layer scaffold: FastAPI + ARQ + Docker (Railway)
- Postgres schema: 7 tables (signals, scored_signals, topics, content_drafts, voice_exemplars, scoring_adjustments, system_alerts)
- Alembic async migration framework with initial migration
- Health endpoint (/health) with DB and Redis connectivity checks
- Decision docs: 003 (SQLAlchemy ORM), 004 (no local dev containers)
```

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/003-sqlalchemy-orm.md docs/decisions/004-no-local-dev-containers.md CHANGELOG.md
git commit -m "docs(worker): add decision docs and update changelog for infra scaffold"
```

---

## Task 17: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
cd worker && pytest -v
```
Expected: All tests pass (models, health endpoint, ping job)

- [ ] **Step 2: Verify Docker build**

```bash
cd worker && docker build -t oj-worker .
```
Expected: Build completes successfully

- [ ] **Step 3: Verify file structure matches spec**

```bash
find worker/ -type f | sort
```
Expected: All files from the spec's directory structure are present

- [ ] **Step 4: Verify no TODO items remain**

```bash
grep -r "TODO\|FIXME\|XXX" worker/ --include="*.py" || echo "No TODOs found"
```
Expected: No TODOs found

- [ ] **Step 5: Push and announce**

```bash
git push origin feature/infra
```

Then announce: _"Ready for PR: `feature/infra` → `develop`"_
