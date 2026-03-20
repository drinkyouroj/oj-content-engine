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
            # AI core
            "artificial intelligence",
            "large language model",
            "ai regulation",
            "ai policy",
            "ai safety",
            "ai governance",
            "open source ai",
            "ai infrastructure",
            # Politics + tech intersection
            "tech regulation",
            "tech policy",
            "digital rights",
            "surveillance",
            "section 230",
        ],
    },
    "direct": {
        "keywords": [
            # AI specific
            "openai",
            "anthropic",
            "deepseek",
            "llama",
            "mistral",
            "gemini",
            "gpt",
            "claude",
            "ai agent",
            "ai tooling",
            "machine learning",
            "neural network",
            # DePIN (still relevant, lower priority)
            "depin",
            "decentralized infrastructure",
            "helium",
            "filecoin",
            "render network",
            "akash",
            # Politics
            "antitrust",
            "fcc",
            "ftc",
            "congress",
            "executive order",
            "eu ai act",
            # Seahawks/NFL
            "seahawks", "seattle seahawks", "nfl", "mike macdonald",
            "geno smith", "jaxon smith-njigba", "nfc west",
            # Media
            "media criticism", "false balance", "journalism ethics",
        ],
    },
    "adjacent": {
        "keywords": [
            # Broader tech/infra
            "decentralized compute",
            "blockchain infrastructure",
            "crypto infrastructure",
            "web3 infrastructure",
            "cloud computing",
            "edge computing",
            "data sovereignty",
            "content moderation",
            "platform governance",
            "creator economy",
            "indie hacker",
            "solopreneur",
            # Broader sports/media
            "salary cap", "nfl draft", "football analytics",
            "narrative framing",
            "neurodivergence", "autism", "indie creator",
        ],
    },
}

RESONANCE_SCORES: dict[str, int] = {
    "core": 100,
    "direct": 60,
    "adjacent": 30,
    "none": 0,
}
