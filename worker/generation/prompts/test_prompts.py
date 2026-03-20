"""Snapshot tests for prompt template assembly.

Verifies that each platform prompt correctly injects topic context, thesis,
and exemplar content, and that the system prompt contains required brand
voice elements.
"""
from __future__ import annotations

from worker.generation.prompts.substack import build_prompt as build_substack
from worker.generation.prompts.twitter import build_prompt as build_twitter
from worker.generation.prompts.linkedin import build_prompt as build_linkedin
from worker.generation.prompts.instagram import build_prompt as build_instagram
from worker.generation.prompts.system import build_system_prompt

_SCORE_BREAKDOWN = {
    "signal_strength": 80, "timing_window": 70, "depth_potential": 75,
    "novelty": 65, "community_resonance": 60, "brand_angle_availability": 80,
}


class TestSystemPrompt:
    def test_contains_voice_rules(self):
        prompt = build_system_prompt()
        assert "intellectual stand-up comedy" in prompt.lower() or "witty" in prompt.lower()

    def test_contains_hard_bans(self):
        prompt = build_system_prompt()
        assert "em dash" in prompt.lower() or "\u2014" in prompt

    def test_contains_personal_context(self):
        prompt = build_system_prompt()
        assert "Seattle" in prompt or "Michigan" in prompt

    def test_contains_banned_words(self):
        prompt = build_system_prompt()
        assert "delve" in prompt
        assert "tapestry" in prompt

    def test_contains_active_voice_rule(self):
        prompt = build_system_prompt()
        assert "active voice" in prompt.lower()

    def test_contains_metaphor_rule(self):
        prompt = build_system_prompt()
        assert "metaphor" in prompt.lower()


class TestPromptAssembly:
    def test_substack_contains_topic_title(self):
        prompt = build_substack("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, "My thesis", [])
        assert "AI Safety Theater" in prompt
        assert "My thesis" in prompt

    def test_substack_without_thesis(self):
        prompt = build_substack("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, None, [])
        assert "AI Safety Theater" in prompt
        assert "AI-originated" in prompt or "no thesis" in prompt.lower()

    def test_substack_contains_template_instructions(self):
        prompt = build_substack("Test", "Body", _SCORE_BREAKDOWN, None, [])
        assert "Triple Connection" in prompt or "TRIPLE CONNECTION" in prompt
        assert "System Audit" in prompt or "SYSTEM AUDIT" in prompt
        assert "1,500" in prompt or "1500" in prompt

    def test_substack_contains_word_count(self):
        prompt = build_substack("Test", "Body", _SCORE_BREAKDOWN, None, [])
        assert "1,700" in prompt or "1700" in prompt

    def test_twitter_contains_tweet_constraints(self):
        prompt = build_twitter("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, None, [])
        assert "280" in prompt
        assert "AI Safety Theater" in prompt

    def test_twitter_contains_thread_structure(self):
        prompt = build_twitter("Test", "Body", _SCORE_BREAKDOWN, None, [])
        assert "hook" in prompt.lower()
        assert "5" in prompt and "12" in prompt

    def test_linkedin_contains_topic(self):
        prompt = build_linkedin("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, None, [])
        assert "AI Safety Theater" in prompt

    def test_linkedin_contains_word_count(self):
        prompt = build_linkedin("Test", "Body", _SCORE_BREAKDOWN, None, [])
        assert "300" in prompt and "600" in prompt

    def test_linkedin_bans_hustle_porn(self):
        prompt = build_linkedin("Test", "Body", _SCORE_BREAKDOWN, None, [])
        assert "hustle" in prompt.lower() or "humbled" in prompt.lower()

    def test_instagram_contains_topic(self):
        prompt = build_instagram("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, None, [])
        assert "AI Safety Theater" in prompt

    def test_instagram_contains_image_card_separator(self):
        prompt = build_instagram("Test", "Body", _SCORE_BREAKDOWN, None, [])
        assert "---IMAGE CARD---" in prompt

    def test_instagram_contains_caption_limit(self):
        prompt = build_instagram("Test", "Body", _SCORE_BREAKDOWN, None, [])
        assert "150" in prompt

    def test_exemplars_injected(self):
        exemplars = ["Example post about DePIN infrastructure"]
        prompt = build_substack("Test Topic", "Body", _SCORE_BREAKDOWN, None, exemplars)
        assert "DePIN infrastructure" in prompt

    def test_exemplars_injected_twitter(self):
        exemplars = ["A punchy tweet about node economics"]
        prompt = build_twitter("Test", "Body", _SCORE_BREAKDOWN, None, exemplars)
        assert "node economics" in prompt

    def test_exemplars_injected_linkedin(self):
        exemplars = ["LinkedIn post about decentralized compute"]
        prompt = build_linkedin("Test", "Body", _SCORE_BREAKDOWN, None, exemplars)
        assert "decentralized compute" in prompt

    def test_exemplars_injected_instagram(self):
        exemplars = ["Instagram caption about AI regulation"]
        prompt = build_instagram("Test", "Body", _SCORE_BREAKDOWN, None, exemplars)
        assert "AI regulation" in prompt

    def test_score_breakdown_formatted(self):
        prompt = build_substack("Test", "Body", _SCORE_BREAKDOWN, None, [])
        assert "Signal Strength" in prompt or "signal_strength" in prompt
        assert "80" in prompt

    def test_all_platforms_include_topic_body(self):
        body = "Unique body text for assertion check"
        for builder in [build_substack, build_twitter, build_linkedin, build_instagram]:
            prompt = builder("Title", body, _SCORE_BREAKDOWN, None, [])
            assert body in prompt, f"{builder.__module__} did not include topic body"

    def test_thesis_present_when_provided(self):
        for builder in [build_substack, build_twitter, build_linkedin, build_instagram]:
            prompt = builder("Title", "Body", _SCORE_BREAKDOWN, "My specific thesis", [])
            assert "My specific thesis" in prompt, f"{builder.__module__} did not include thesis"

    def test_no_thesis_flag_when_absent(self):
        for builder in [build_substack, build_twitter, build_linkedin, build_instagram]:
            prompt = builder("Title", "Body", _SCORE_BREAKDOWN, None, [])
            assert "AI-originated" in prompt or "no thesis" in prompt.lower(), (
                f"{builder.__module__} did not flag missing thesis"
            )
