"""Tests for vertical detection from topic text."""
from __future__ import annotations

import pytest

from worker.generation.verticals import detect_vertical, VERTICAL_KEYWORDS


class TestDetectVertical:
    def test_seahawks_topic(self):
        assert detect_vertical("Seahawks draft Jaxon Smith-Njigba", "") == "sports_seahawks"

    def test_ai_topic(self):
        assert detect_vertical("OpenAI releases new AI safety framework", "") == "ai_politics"

    def test_depin_topic(self):
        assert detect_vertical("Helium network reaches 1M hotspots", "") == "depin"

    def test_media_topic(self):
        assert detect_vertical("False balance in journalism undermines truth", "") == "media"

    def test_personal_topic(self):
        assert detect_vertical("Living with autism as a systems thinker", "") == "personal"

    def test_body_fallback(self):
        """If title has no match, check body."""
        assert detect_vertical("Interesting article", "The FTC announced new antitrust rules") == "ai_politics"

    def test_no_match_returns_general(self):
        assert detect_vertical("Random unrelated topic", "Nothing relevant here") == "general"

    def test_case_insensitive(self):
        assert detect_vertical("SEAHAWKS Win NFC West", "") == "sports_seahawks"

    def test_keyword_constants_exist(self):
        assert "ai_politics" in VERTICAL_KEYWORDS
        assert "depin" in VERTICAL_KEYWORDS
        assert "sports_seahawks" in VERTICAL_KEYWORDS
        assert "media" in VERTICAL_KEYWORDS
        assert "personal" in VERTICAL_KEYWORDS
