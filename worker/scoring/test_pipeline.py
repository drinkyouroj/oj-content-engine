"""
Tests for the scoring pipeline orchestrator.

Mocks Pass 1, Pass 2, and adjustments to test the full pipeline flow,
pre-filter cutoff, timing cap logic, and composite score computation.
All tests run without network, API keys, or a real database.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.app.models.scored_signal import ScoringStatus
from worker.scoring.pipeline import _compute_composite, score_signal
from worker.scoring.rubric import WEIGHTS


def _make_signal_row(signal_id: uuid.UUID | None = None) -> SimpleNamespace:
    """Create a fake Signal row returned from DB."""
    return SimpleNamespace(
        id=signal_id or uuid.uuid4(),
        title="Test Signal",
        body_preview="Some preview",
        source="rss",
    )


def _mock_session(signal: SimpleNamespace | None = None) -> AsyncMock:
    """Create a mock session that returns the given signal on query."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = signal
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestComputeComposite:
    """Tests for _compute_composite helper."""

    def test_all_zeros(self):
        """All zero scores produce composite 0."""
        breakdown = {dim: 0 for dim in WEIGHTS}
        assert _compute_composite(breakdown) == 0.0

    def test_all_hundreds(self):
        """All 100 scores produce composite 100."""
        breakdown = {dim: 100 for dim in WEIGHTS}
        assert abs(_compute_composite(breakdown) - 100.0) < 1e-9

    def test_weighted_correctly(self):
        """Composite reflects weights accurately."""
        breakdown = {
            "signal_strength": 100,
            "timing_window": 0,
            "depth_potential": 0,
            "novelty": 0,
            "community_resonance": 0,
            "brand_angle_availability": 0,
        }
        expected = 100 * WEIGHTS["signal_strength"]
        assert abs(_compute_composite(breakdown) - expected) < 1e-9


class TestScoreSignal:
    """Tests for the score_signal orchestrator."""

    @pytest.mark.asyncio
    async def test_signal_not_found_raises(self):
        """ValueError raised if signal_id doesn't exist."""
        session = _mock_session(signal=None)
        with pytest.raises(ValueError, match="not found"):
            await score_signal(uuid.uuid4(), session, "sk-test")

    @pytest.mark.asyncio
    async def test_prefilter_cutoff(self):
        """Signals below pre-filter threshold skip Pass 2."""
        signal = _make_signal_row()
        session = _mock_session(signal)

        # Pass 1 returns very low scores
        low_scores = {"signal_strength": 10, "timing_window": 10, "community_resonance": 0}

        with (
            patch(
                "worker.scoring.pipeline.compute_pass1_scores",
                new_callable=AsyncMock,
                return_value=low_scores,
            ),
            patch(
                "worker.scoring.pipeline.apply_adjustments",
                new_callable=AsyncMock,
                return_value=low_scores,
            ),
            patch(
                "worker.scoring.pipeline.score_with_llm",
                new_callable=AsyncMock,
            ) as mock_llm,
        ):
            result = await score_signal(signal.id, session, "sk-test")

        # LLM should NOT have been called
        mock_llm.assert_not_called()
        assert result.status == ScoringStatus.SCORED
        assert result.pass2_completed_at is None
        assert result.score_breakdown["depth_potential"] == 0

    @pytest.mark.asyncio
    async def test_full_pipeline_with_pass2(self):
        """Signals above pre-filter proceed to Pass 2."""
        signal = _make_signal_row()
        session = _mock_session(signal)

        pass1_scores = {
            "signal_strength": 70,
            "timing_window": 80,
            "community_resonance": 60,
        }
        pass2_scores = {
            "depth_potential": 75,
            "novelty": 65,
            "brand_angle_availability": 80,
        }

        with (
            patch(
                "worker.scoring.pipeline.compute_pass1_scores",
                new_callable=AsyncMock,
                return_value=dict(pass1_scores),
            ),
            patch(
                "worker.scoring.pipeline.apply_adjustments",
                new_callable=AsyncMock,
                return_value=dict(pass1_scores),
            ),
            patch(
                "worker.scoring.pipeline.score_with_llm",
                new_callable=AsyncMock,
                return_value=pass2_scores,
            ),
        ):
            result = await score_signal(signal.id, session, "sk-test")

        assert result.status == ScoringStatus.SCORED
        assert result.pass1_completed_at is not None
        assert result.pass2_completed_at is not None

        # Verify all 6 dimensions in breakdown
        bd = result.score_breakdown
        assert set(bd.keys()) == set(WEIGHTS.keys())
        assert bd["signal_strength"] == 70
        assert bd["depth_potential"] == 75

    @pytest.mark.asyncio
    async def test_timing_cap_applied(self):
        """Timing capped to 70 when timing==100 and novelty<50."""
        signal = _make_signal_row()
        session = _mock_session(signal)

        pass1_scores = {
            "signal_strength": 70,
            "timing_window": 100,
            "community_resonance": 60,
        }
        pass2_scores = {
            "depth_potential": 75,
            "novelty": 40,  # < 50, triggers cap
            "brand_angle_availability": 80,
        }

        with (
            patch(
                "worker.scoring.pipeline.compute_pass1_scores",
                new_callable=AsyncMock,
                return_value=dict(pass1_scores),
            ),
            patch(
                "worker.scoring.pipeline.apply_adjustments",
                new_callable=AsyncMock,
                return_value=dict(pass1_scores),
            ),
            patch(
                "worker.scoring.pipeline.score_with_llm",
                new_callable=AsyncMock,
                return_value=pass2_scores,
            ),
        ):
            result = await score_signal(signal.id, session, "sk-test")

        # Timing should be capped to 70
        assert result.score_breakdown["timing_window"] == 70

    @pytest.mark.asyncio
    async def test_timing_no_cap_when_novelty_high(self):
        """Timing stays at 100 when novelty >= 50."""
        signal = _make_signal_row()
        session = _mock_session(signal)

        pass1_scores = {
            "signal_strength": 70,
            "timing_window": 100,
            "community_resonance": 60,
        }
        pass2_scores = {
            "depth_potential": 75,
            "novelty": 50,  # exactly 50, no cap
            "brand_angle_availability": 80,
        }

        with (
            patch(
                "worker.scoring.pipeline.compute_pass1_scores",
                new_callable=AsyncMock,
                return_value=dict(pass1_scores),
            ),
            patch(
                "worker.scoring.pipeline.apply_adjustments",
                new_callable=AsyncMock,
                return_value=dict(pass1_scores),
            ),
            patch(
                "worker.scoring.pipeline.score_with_llm",
                new_callable=AsyncMock,
                return_value=pass2_scores,
            ),
        ):
            result = await score_signal(signal.id, session, "sk-test")

        assert result.score_breakdown["timing_window"] == 100

    @pytest.mark.asyncio
    async def test_composite_score_calculated(self):
        """Composite score matches weighted sum of all dimensions."""
        signal = _make_signal_row()
        session = _mock_session(signal)

        pass1_scores = {
            "signal_strength": 80,
            "timing_window": 60,
            "community_resonance": 100,
        }
        pass2_scores = {
            "depth_potential": 70,
            "novelty": 55,
            "brand_angle_availability": 90,
        }

        with (
            patch(
                "worker.scoring.pipeline.compute_pass1_scores",
                new_callable=AsyncMock,
                return_value=dict(pass1_scores),
            ),
            patch(
                "worker.scoring.pipeline.apply_adjustments",
                new_callable=AsyncMock,
                return_value=dict(pass1_scores),
            ),
            patch(
                "worker.scoring.pipeline.score_with_llm",
                new_callable=AsyncMock,
                return_value=pass2_scores,
            ),
        ):
            result = await score_signal(signal.id, session, "sk-test")

        expected = (
            80 * 0.25
            + 60 * 0.15
            + 70 * 0.15
            + 55 * 0.15
            + 100 * 0.10
            + 90 * 0.20
        )
        assert abs(result.composite_score - expected) < 1e-9
