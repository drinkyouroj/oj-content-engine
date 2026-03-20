"""
Tests for Pass 1 rule-based scoring functions.

Tests each scorer with fixture signals and mocked DB queries.
All tests run without network, API keys, or a real database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.scoring.pass1 import (
    compute_pass1_scores,
    score_community_resonance,
    score_signal_strength,
    score_timing_window,
)


def _make_signal(
    *,
    title: str = "Test Signal",
    body_preview: str | None = None,
    discovered_at: datetime | None = None,
    source: str = "rss",
    dedup_hash: str = "abc123",
    signal_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    """Create a fake signal object for testing."""
    return SimpleNamespace(
        id=signal_id or uuid.uuid4(),
        title=title,
        body_preview=body_preview,
        discovered_at=discovered_at or datetime.now(timezone.utc),
        source=source,
        dedup_hash=dedup_hash,
        source_metrics=None,
    )


def _mock_session_with_sources(sources: list[str]) -> AsyncMock:
    """Create a mock session that returns the given source values."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(s,) for s in sources]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ---------------------------------------------------------------------------
# score_signal_strength
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_strength_single_source():
    """A signal with no corroboration scores 10."""
    signal = _make_signal()
    session = _mock_session_with_sources([])  # No corroborating signals
    score = await score_signal_strength(signal, session)
    assert score == 10


@pytest.mark.asyncio
async def test_signal_strength_two_sources():
    """A signal corroborated by one other source scores 40."""
    signal = _make_signal(source="rss")
    session = _mock_session_with_sources(["reddit"])
    score = await score_signal_strength(signal, session)
    assert score == 40


@pytest.mark.asyncio
async def test_signal_strength_three_plus_cross_platform():
    """3+ distinct cross-platform sources score 100."""
    signal = _make_signal(source="rss")
    session = _mock_session_with_sources(["reddit", "hn"])
    score = await score_signal_strength(signal, session)
    assert score == 100


@pytest.mark.asyncio
async def test_signal_strength_three_same_platform():
    """3+ signals but only 2 distinct sources scores 40."""
    signal = _make_signal(source="rss")
    # Two corroborating signals but one is same source as original
    session = _mock_session_with_sources(["rss", "reddit"])
    score = await score_signal_strength(signal, session)
    # rss + rss + reddit = 2 distinct sources
    assert score == 40


# ---------------------------------------------------------------------------
# score_timing_window
# ---------------------------------------------------------------------------


def test_timing_very_fresh():
    """Signal < 48 hours old scores 100."""
    signal = _make_signal(discovered_at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert score_timing_window(signal) == 100


def test_timing_48_to_72_hours():
    """Signal 48-72 hours old scores 80."""
    signal = _make_signal(discovered_at=datetime.now(timezone.utc) - timedelta(hours=60))
    assert score_timing_window(signal) == 80


def test_timing_3_to_7_days():
    """Signal 3-7 days old scores 50."""
    signal = _make_signal(discovered_at=datetime.now(timezone.utc) - timedelta(days=5))
    assert score_timing_window(signal) == 50


def test_timing_over_7_days():
    """Signal > 7 days old scores 30."""
    signal = _make_signal(discovered_at=datetime.now(timezone.utc) - timedelta(days=10))
    assert score_timing_window(signal) == 30


# ---------------------------------------------------------------------------
# score_community_resonance
# ---------------------------------------------------------------------------


def test_resonance_core_keyword():
    """Core keyword 'depin' in title scores 100."""
    signal = _make_signal(title="DePIN Revolution in Wireless Networks")
    assert score_community_resonance(signal) == 100


def test_resonance_core_keyword_in_body():
    """Core keyword in body_preview also matches."""
    signal = _make_signal(
        title="Something unrelated",
        body_preview="This article covers decentralized infrastructure projects",
    )
    assert score_community_resonance(signal) == 100


def test_resonance_direct_keyword():
    """Direct keyword 'helium' scores 60."""
    signal = _make_signal(title="Helium Network Reaches 1M Hotspots")
    assert score_community_resonance(signal) == 60


def test_resonance_adjacent_keyword():
    """Adjacent keyword 'ai tooling' scores 30."""
    signal = _make_signal(title="New AI Tooling for Developers")
    assert score_community_resonance(signal) == 30


def test_resonance_no_match():
    """No matching keywords scores 0."""
    signal = _make_signal(title="Weather forecast for tomorrow")
    assert score_community_resonance(signal) == 0


def test_resonance_case_insensitive():
    """Keyword matching is case-insensitive."""
    signal = _make_signal(title="DEPIN IS THE FUTURE")
    assert score_community_resonance(signal) == 100


def test_resonance_highest_tier_wins():
    """If multiple tiers match, highest tier score wins."""
    signal = _make_signal(
        title="DePIN Project Helium Expands",
        body_preview="A web3 infrastructure initiative",
    )
    # core (depin) = 100 should win over direct (helium) = 60
    assert score_community_resonance(signal) == 100


# ---------------------------------------------------------------------------
# compute_pass1_scores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_pass1_returns_all_keys():
    """compute_pass1_scores returns all 3 Pass 1 dimension keys."""
    signal = _make_signal(title="DePIN test signal")
    session = _mock_session_with_sources([])
    result = await compute_pass1_scores(signal, session)
    assert set(result.keys()) == {"signal_strength", "timing_window", "community_resonance"}
    assert all(isinstance(v, int) for v in result.values())
