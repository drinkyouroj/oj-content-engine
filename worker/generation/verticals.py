"""Vertical detection — classify topics into content verticals.

Uses keyword matching against title and body text. Same lightweight
approach as the scoring rubric's resonance taxonomy.

Verticals: ai_politics, depin, sports_seahawks, media, personal, general.
"""
from __future__ import annotations

VERTICAL_KEYWORDS: dict[str, list[str]] = {
    "sports_seahawks": [
        "seahawks", "seattle seahawks", "nfl", "mike macdonald",
        "geno smith", "jaxon smith-njigba", "nfc west", "nfl draft",
        "salary cap", "football analytics", "pete carroll",
    ],
    "ai_politics": [
        "artificial intelligence", "large language model", "ai regulation",
        "ai policy", "ai safety", "ai governance", "open source ai",
        "tech regulation", "tech policy", "digital rights", "surveillance",
        "section 230", "openai", "anthropic", "deepseek", "llama",
        "mistral", "gemini", "gpt", "claude", "ai agent", "ai tooling",
        "antitrust", "fcc", "ftc", "congress", "executive order", "eu ai act",
    ],
    "depin": [
        "depin", "decentralized infrastructure", "helium", "filecoin",
        "render network", "akash", "decentralized compute",
        "blockchain infrastructure", "nodes over numbers",
    ],
    "media": [
        "media criticism", "false balance", "journalism ethics",
        "journalism", "narrative framing", "content moderation",
        "platform governance",
    ],
    "personal": [
        "autism", "neurodivergence", "self-assessment",
        "personal essay", "indie creator", "solopreneur",
    ],
}


def detect_vertical(title: str, body: str) -> str:
    """Detect the content vertical from topic title and body.

    Checks title first (higher signal), then body. Returns the first
    vertical with a keyword match. Returns 'general' if no match.

    Args:
        title: Topic title text.
        body: Topic body preview text.

    Returns:
        Vertical string: ai_politics, depin, sports_seahawks, media, personal, or general.
    """
    combined = f"{title} {body}".lower()

    for vertical, keywords in VERTICAL_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined:
                return vertical

    return "general"
