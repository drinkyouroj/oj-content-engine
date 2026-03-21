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
        assert set(s.value for s in SignalSource) == {"rss", "reddit", "hn", "twitter", "manual"}

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
