"""
Tests for scoring adjustments application.

Mocks DB queries to test keyword matching, dimension adjustment, and clamping.
All tests run without network, API keys, or a real database.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.scoring.adjustments import apply_adjustments


def _make_signal(
    *,
    title: str = "Test Signal",
    body_preview: str | None = None,
) -> SimpleNamespace:
    """Create a fake signal for testing."""
    return SimpleNamespace(title=title, body_preview=body_preview)


def _make_adjustment(keyword: str, dimension: str, adjustment: int) -> SimpleNamespace:
    """Create a fake ScoringAdjustment object."""
    return SimpleNamespace(keyword=keyword, dimension=dimension, adjustment=adjustment)


def _mock_session_with_adjustments(adjustments: list) -> AsyncMock:
    """Create a mock session returning the given adjustments."""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = adjustments
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.mark.asyncio
async def test_no_adjustments():
    """When no adjustments exist, scores are unchanged."""
    scores = {"signal_strength": 50, "timing_window": 80}
    signal = _make_signal()
    session = _mock_session_with_adjustments([])
    result = await apply_adjustments(scores, signal, session)
    assert result == {"signal_strength": 50, "timing_window": 80}


@pytest.mark.asyncio
async def test_matching_keyword_adjusts_score():
    """A matching keyword adjusts the specified dimension."""
    scores = {"signal_strength": 50, "timing_window": 80}
    signal = _make_signal(title="Helium network update")
    adj = _make_adjustment("helium", "signal_strength", 15)
    session = _mock_session_with_adjustments([adj])
    result = await apply_adjustments(scores, signal, session)
    assert result["signal_strength"] == 65
    assert result["timing_window"] == 80  # Unchanged


@pytest.mark.asyncio
async def test_keyword_case_insensitive():
    """Keyword matching is case-insensitive."""
    scores = {"novelty": 60}
    signal = _make_signal(title="HELIUM Expands Coverage")
    adj = _make_adjustment("helium", "novelty", 10)
    session = _mock_session_with_adjustments([adj])
    result = await apply_adjustments(scores, signal, session)
    assert result["novelty"] == 70


@pytest.mark.asyncio
async def test_keyword_matches_body_preview():
    """Keywords in body_preview also trigger adjustments."""
    scores = {"signal_strength": 40}
    signal = _make_signal(
        title="Something else",
        body_preview="This is about helium network expansion",
    )
    adj = _make_adjustment("helium", "signal_strength", 10)
    session = _mock_session_with_adjustments([adj])
    result = await apply_adjustments(scores, signal, session)
    assert result["signal_strength"] == 50


@pytest.mark.asyncio
async def test_clamp_upper_bound():
    """Adjusted score is clamped to 100."""
    scores = {"signal_strength": 95}
    signal = _make_signal(title="helium update")
    adj = _make_adjustment("helium", "signal_strength", 20)
    session = _mock_session_with_adjustments([adj])
    result = await apply_adjustments(scores, signal, session)
    assert result["signal_strength"] == 100


@pytest.mark.asyncio
async def test_clamp_lower_bound():
    """Adjusted score is clamped to 0."""
    scores = {"signal_strength": 5}
    signal = _make_signal(title="helium update")
    adj = _make_adjustment("helium", "signal_strength", -20)
    session = _mock_session_with_adjustments([adj])
    result = await apply_adjustments(scores, signal, session)
    assert result["signal_strength"] == 0


@pytest.mark.asyncio
async def test_non_matching_keyword_ignored():
    """Adjustments with non-matching keywords are ignored."""
    scores = {"signal_strength": 50}
    signal = _make_signal(title="Something about filecoin")
    adj = _make_adjustment("helium", "signal_strength", 20)
    session = _mock_session_with_adjustments([adj])
    result = await apply_adjustments(scores, signal, session)
    assert result["signal_strength"] == 50


@pytest.mark.asyncio
async def test_unknown_dimension_ignored():
    """Adjustments for dimensions not in scores dict are ignored."""
    scores = {"signal_strength": 50}
    signal = _make_signal(title="helium update")
    adj = _make_adjustment("helium", "nonexistent_dim", 10)
    session = _mock_session_with_adjustments([adj])
    result = await apply_adjustments(scores, signal, session)
    assert result == {"signal_strength": 50}


@pytest.mark.asyncio
async def test_multiple_adjustments_stack():
    """Multiple matching adjustments for the same dimension stack."""
    scores = {"signal_strength": 50}
    signal = _make_signal(title="helium depin project")
    adj1 = _make_adjustment("helium", "signal_strength", 10)
    adj2 = _make_adjustment("depin", "signal_strength", 15)
    session = _mock_session_with_adjustments([adj1, adj2])
    result = await apply_adjustments(scores, signal, session)
    assert result["signal_strength"] == 75
