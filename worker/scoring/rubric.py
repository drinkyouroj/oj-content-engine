"""
Scoring rubric constants: weights, thresholds, and keyword taxonomy.

Implements PRD Section 3 (Topic Triage Rubric).
These constants define how the six scoring dimensions are weighted to produce
a composite score, what thresholds control pipeline flow, and which keywords
map to Community Resonance tiers.

Inputs: None (pure constants).
Outputs: Importable dicts/ints consumed by pass1, pass2, pipeline modules.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Dimension weights — must sum to 1.0
# ---------------------------------------------------------------------------
WEIGHTS: dict[str, float] = {
    "signal_strength": 0.25,
    "timing_window": 0.15,
    "depth_potential": 0.15,
    "novelty": 0.15,
    "community_resonance": 0.10,
    "brand_angle_availability": 0.20,
}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
# Signals scoring at or below this after Pass 1 skip the LLM call entirely.
PASS1_PREFILTER_THRESHOLD: int = 30

# Composite score required to auto-queue for content generation.
THRESHOLD_QUEUE: int = 65

# Composite score required to surface for human review (below QUEUE).
THRESHOLD_REVIEW: int = 55

# ---------------------------------------------------------------------------
# Keyword taxonomy for Community Resonance scoring
# ---------------------------------------------------------------------------
RESONANCE_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "core": {
        "keywords": [
            "depin",
            "decentralized infrastructure",
            "decentralized physical infrastructure",
        ],
    },
    "direct": {
        "keywords": [
            "helium",
            "hivemapper",
            "filecoin",
            "render network",
            "akash",
            "io.net",
            "peaq",
            "dimo",
            "weatherxm",
            "natix",
            "geodnet",
        ],
    },
    "adjacent": {
        "keywords": [
            "web3 infrastructure",
            "blockchain infrastructure",
            "decentralized compute",
            "decentralized storage",
            "ai tooling",
            "open source ai",
            "crypto infrastructure",
        ],
    },
}

RESONANCE_SCORES: dict[str, int] = {
    "core": 100,
    "direct": 60,
    "adjacent": 30,
    "none": 0,
}
