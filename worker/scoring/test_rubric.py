"""
Tests for scoring rubric constants.

Verifies that weights sum to 1.0, thresholds are sensible, and the
keyword taxonomy is properly structured.
"""

from __future__ import annotations

from worker.scoring.rubric import (
    PASS1_PREFILTER_THRESHOLD,
    RESONANCE_SCORES,
    RESONANCE_TAXONOMY,
    THRESHOLD_QUEUE,
    THRESHOLD_REVIEW,
    WEIGHTS,
)


def test_weights_sum_to_one():
    """Weights across all 6 dimensions must sum to 1.0."""
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_weights_has_six_dimensions():
    """There must be exactly 6 scoring dimensions."""
    expected = {
        "signal_strength",
        "timing_window",
        "depth_potential",
        "novelty",
        "community_resonance",
        "brand_angle_availability",
    }
    assert set(WEIGHTS.keys()) == expected


def test_all_weights_positive():
    """Every weight must be positive."""
    for dim, weight in WEIGHTS.items():
        assert weight > 0, f"Weight for {dim} is not positive: {weight}"


def test_threshold_ordering():
    """REVIEW < QUEUE, and pre-filter is the lowest."""
    assert PASS1_PREFILTER_THRESHOLD < THRESHOLD_REVIEW
    assert THRESHOLD_REVIEW < THRESHOLD_QUEUE


def test_resonance_taxonomy_tiers():
    """Taxonomy must have core, direct, and adjacent tiers with keywords."""
    for tier in ("core", "direct", "adjacent"):
        assert tier in RESONANCE_TAXONOMY
        assert "keywords" in RESONANCE_TAXONOMY[tier]
        assert len(RESONANCE_TAXONOMY[tier]["keywords"]) > 0


def test_resonance_scores_match_taxonomy():
    """Every taxonomy tier plus 'none' must have a corresponding score."""
    expected_tiers = set(RESONANCE_TAXONOMY.keys()) | {"none"}
    assert set(RESONANCE_SCORES.keys()) == expected_tiers


def test_resonance_scores_descending():
    """core > direct > adjacent > none."""
    assert RESONANCE_SCORES["core"] > RESONANCE_SCORES["direct"]
    assert RESONANCE_SCORES["direct"] > RESONANCE_SCORES["adjacent"]
    assert RESONANCE_SCORES["adjacent"] > RESONANCE_SCORES["none"]
    assert RESONANCE_SCORES["none"] == 0
