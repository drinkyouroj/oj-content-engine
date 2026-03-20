"""
Unit tests for the triage engine.

Tests hard gates, threshold logic, and the full triage pipeline
with mocked database sessions. No network or database required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.app.models.scored_signal import ScoringStatus
from worker.app.models.topic import TopicStatus
from worker.triage.engine import (
    HARD_GATE_BRAND_ANGLE,
    HARD_GATE_COMMUNITY_RESONANCE,
    apply_hard_gates,
    determine_topic_status,
    triage_scored_signal,
    run_triage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_scored_signal(
    *,
    composite_score: float = 60.0,
    community_resonance: int = 60,
    brand_angle: int = 60,
    signal_strength: int = 40,
    timing_window: int = 80,
    depth_potential: int = 50,
    novelty: int = 50,
) -> MagicMock:
    """Create a mock ScoredSignal with configurable scores."""
    ss = MagicMock()
    ss.id = uuid.uuid4()
    ss.signal_id = uuid.uuid4()
    ss.composite_score = composite_score
    ss.status = ScoringStatus.SCORED
    ss.score_breakdown = {
        "signal_strength": signal_strength,
        "timing_window": timing_window,
        "community_resonance": community_resonance,
        "brand_angle_availability": brand_angle,
        "depth_potential": depth_potential,
        "novelty": novelty,
    }
    return ss


# ---------------------------------------------------------------------------
# apply_hard_gates
# ---------------------------------------------------------------------------


class TestHardGates:
    """Tests for the hard gate logic."""

    def test_passes_when_both_above_threshold(self):
        breakdown = {"community_resonance": 60, "brand_angle_availability": 80}
        assert apply_hard_gates(breakdown) is None

    def test_fails_on_low_community_resonance(self):
        breakdown = {"community_resonance": 10, "brand_angle_availability": 80}
        result = apply_hard_gates(breakdown)
        assert result is not None
        assert "community_resonance" in result

    def test_fails_on_low_brand_angle(self):
        breakdown = {"community_resonance": 60, "brand_angle_availability": 5}
        result = apply_hard_gates(breakdown)
        assert result is not None
        assert "brand_angle_availability" in result

    def test_fails_on_both_low(self):
        """When both fail, community resonance is checked first."""
        breakdown = {"community_resonance": 0, "brand_angle_availability": 0}
        result = apply_hard_gates(breakdown)
        assert "community_resonance" in result

    def test_boundary_at_threshold(self):
        """Exactly at threshold (20) should pass."""
        breakdown = {"community_resonance": 20, "brand_angle_availability": 20}
        assert apply_hard_gates(breakdown) is None

    def test_boundary_just_below_threshold(self):
        """One below threshold (19) should fail."""
        breakdown = {"community_resonance": 19, "brand_angle_availability": 60}
        assert apply_hard_gates(breakdown) is not None

    def test_missing_keys_default_to_zero(self):
        """Missing keys should default to 0 (fail)."""
        assert apply_hard_gates({}) is not None

    def test_threshold_constants(self):
        assert HARD_GATE_COMMUNITY_RESONANCE == 20
        assert HARD_GATE_BRAND_ANGLE == 20


# ---------------------------------------------------------------------------
# determine_topic_status
# ---------------------------------------------------------------------------


class TestDetermineStatus:
    """Tests for composite score threshold logic."""

    def test_queued_at_65(self):
        assert determine_topic_status(65.0) == TopicStatus.QUEUED

    def test_queued_above_65(self):
        assert determine_topic_status(85.0) == TopicStatus.QUEUED

    def test_review_at_55(self):
        assert determine_topic_status(55.0) == TopicStatus.REVIEW

    def test_review_at_64(self):
        assert determine_topic_status(64.9) == TopicStatus.REVIEW

    def test_archived_at_54(self):
        assert determine_topic_status(54.9) == TopicStatus.ARCHIVED

    def test_archived_at_zero(self):
        assert determine_topic_status(0.0) == TopicStatus.ARCHIVED

    def test_queued_at_100(self):
        assert determine_topic_status(100.0) == TopicStatus.QUEUED


# ---------------------------------------------------------------------------
# triage_scored_signal
# ---------------------------------------------------------------------------


class TestTriageScoredSignal:
    """Tests for the single-signal triage function."""

    @pytest.mark.asyncio
    async def test_hard_gate_archives(self):
        """Signal failing hard gate is archived regardless of composite."""
        ss = _make_scored_signal(composite_score=90.0, community_resonance=5)
        session = AsyncMock()

        topic = await triage_scored_signal(ss, session)

        assert topic.status == TopicStatus.ARCHIVED
        assert "hard_gate" in topic.review_decision
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_score_queued(self):
        """Signal with composite >= 65 and passing hard gates is queued."""
        ss = _make_scored_signal(composite_score=70.0)
        session = AsyncMock()

        topic = await triage_scored_signal(ss, session)

        assert topic.status == TopicStatus.QUEUED
        assert topic.queued_at is not None

    @pytest.mark.asyncio
    async def test_medium_score_review(self):
        """Signal with composite 55-64 is flagged for review."""
        ss = _make_scored_signal(composite_score=60.0)
        session = AsyncMock()

        topic = await triage_scored_signal(ss, session)

        assert topic.status == TopicStatus.REVIEW
        assert topic.queued_at is None

    @pytest.mark.asyncio
    async def test_low_score_archived(self):
        """Signal with composite < 55 is archived."""
        ss = _make_scored_signal(composite_score=40.0)
        session = AsyncMock()

        topic = await triage_scored_signal(ss, session)

        assert topic.status == TopicStatus.ARCHIVED
        assert topic.queued_at is None

    @pytest.mark.asyncio
    async def test_brand_angle_hard_gate(self):
        """Signal with low brand angle is archived even with high composite."""
        ss = _make_scored_signal(composite_score=80.0, brand_angle=10)
        session = AsyncMock()

        topic = await triage_scored_signal(ss, session)

        assert topic.status == TopicStatus.ARCHIVED
        assert "brand_angle" in topic.review_decision


# ---------------------------------------------------------------------------
# run_triage
# ---------------------------------------------------------------------------


class TestRunTriage:
    """Tests for the batch triage function."""

    @pytest.mark.asyncio
    async def test_triages_unprocessed_signals(self):
        """Processes all scored signals without topics."""
        ss1 = _make_scored_signal(composite_score=70.0)
        ss2 = _make_scored_signal(composite_score=60.0)
        ss3 = _make_scored_signal(composite_score=30.0)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [ss1, ss2, ss3]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        counts = await run_triage(session)

        assert counts["queued"] == 1
        assert counts["review"] == 1
        assert counts["archived"] == 1
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_when_nothing_to_process(self):
        """Returns all zeros when no unprocessed signals exist."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        counts = await run_triage(session)

        assert counts == {"queued": 0, "review": 0, "archived": 0}

    @pytest.mark.asyncio
    async def test_hard_gated_signals_counted_as_archived(self):
        """Signals failing hard gates are counted in the archived bucket."""
        ss = _make_scored_signal(composite_score=90.0, community_resonance=0)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [ss]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        counts = await run_triage(session)

        assert counts["archived"] == 1
        assert counts["queued"] == 0
