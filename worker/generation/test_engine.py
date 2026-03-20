"""Tests for the content generation engine orchestrator.

Verifies that generate_for_topic() correctly ties together vertical detection,
exemplar selection, prompt assembly, LLM generation, and voice-drift critique
to produce ContentDraft rows.

Implements PRD Section 4 (Content Generation Engine).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.app.models.content_draft import ContentDraft, DraftStatus, Platform
from worker.app.models.topic import TopicStatus
from worker.generation.engine import generate_for_topic
from worker.generation.llm_client import LLMGenerationError, LLMResponse


def _make_topic(thesis: str | None = None, composite_score: float = 70.0) -> MagicMock:
    """Create a mock Topic with nested ScoredSignal -> Signal.

    Args:
        thesis: Optional thesis string. Sets thesis_provided accordingly.
        composite_score: Composite score for the scored signal.

    Returns:
        MagicMock configured to behave like a Topic instance.
    """
    topic = MagicMock()
    topic.id = uuid.uuid4()
    topic.status = TopicStatus.QUEUED
    topic.thesis = thesis
    topic.thesis_provided = thesis is not None
    topic.vertical = None

    signal = MagicMock()
    signal.title = "Test Topic About AI Safety"
    signal.body_preview = "A deep dive into AI safety frameworks"
    signal.source_metrics = {"upvotes": 100}

    scored_signal = MagicMock()
    scored_signal.composite_score = composite_score
    scored_signal.score_breakdown = {
        "signal_strength": 80,
        "timing_window": 70,
        "depth_potential": 75,
        "novelty": 65,
        "community_resonance": 60,
        "brand_angle_availability": 80,
    }
    scored_signal.signal = signal

    topic.scored_signal = scored_signal
    return topic


def _make_llm_response(content: str = "Generated content") -> LLMResponse:
    """Create a standard LLMResponse for testing."""
    return LLMResponse(
        content=content,
        total_tokens=500,
        model="test",
        provider="groq",
    )


class TestGenerateForTopic:
    """Tests for the generate_for_topic orchestrator."""

    @pytest.mark.asyncio
    @patch("worker.generation.engine.select_exemplars", new_callable=AsyncMock, return_value=[])
    @patch("worker.generation.engine.detect_vertical", return_value="ai_politics")
    async def test_generates_4_platform_drafts(
        self, _mock_vertical: MagicMock, _mock_exemplars: AsyncMock
    ) -> None:
        """Verify 4 drafts are created, one per platform."""
        topic = _make_topic(thesis="AI safety needs nuance")
        session = AsyncMock()
        llm_client = AsyncMock()
        llm_client.generate = AsyncMock(return_value=_make_llm_response())

        drafts = await generate_for_topic(topic, session, llm_client)

        assert len(drafts) == 4
        platforms = {d.platform for d in drafts}
        assert platforms == {
            Platform.SUBSTACK,
            Platform.TWITTER,
            Platform.LINKEDIN,
            Platform.INSTAGRAM,
        }
        for draft in drafts:
            assert draft.status == DraftStatus.DRAFT
            assert draft.topic_id == topic.id
            assert draft.content == "Generated content"

    @pytest.mark.asyncio
    @patch("worker.generation.engine.select_exemplars", new_callable=AsyncMock, return_value=[])
    @patch("worker.generation.engine.detect_vertical", return_value="ai_politics")
    @patch("worker.generation.engine.run_voice_critique", new_callable=AsyncMock)
    async def test_substack_gets_voice_critique(
        self,
        mock_critique: AsyncMock,
        _mock_vertical: MagicMock,
        _mock_exemplars: AsyncMock,
    ) -> None:
        """Verify run_voice_critique is called once and Substack draft uses revised content."""
        mock_critique.return_value = LLMResponse(
            content="Revised Substack content",
            total_tokens=600,
            model="test",
            provider="groq",
        )
        topic = _make_topic(thesis="Test thesis")
        session = AsyncMock()
        llm_client = AsyncMock()
        llm_client.generate = AsyncMock(return_value=_make_llm_response())

        drafts = await generate_for_topic(topic, session, llm_client)

        mock_critique.assert_called_once()
        substack_drafts = [d for d in drafts if d.platform == Platform.SUBSTACK]
        assert len(substack_drafts) == 1
        assert substack_drafts[0].content == "Revised Substack content"
        assert substack_drafts[0].generation_metadata.get("voice_drift_applied") is True

    @pytest.mark.asyncio
    @patch("worker.generation.engine.select_exemplars", new_callable=AsyncMock, return_value=[])
    @patch("worker.generation.engine.detect_vertical", return_value="general")
    async def test_no_thesis_sets_ai_originated_flag(
        self, _mock_vertical: MagicMock, _mock_exemplars: AsyncMock
    ) -> None:
        """Verify generation_metadata['ai_originated'] is True when no thesis provided."""
        topic = _make_topic(thesis=None)
        session = AsyncMock()
        llm_client = AsyncMock()
        llm_client.generate = AsyncMock(return_value=_make_llm_response())

        drafts = await generate_for_topic(topic, session, llm_client)

        for draft in drafts:
            assert draft.generation_metadata["ai_originated"] is True

    @pytest.mark.asyncio
    @patch("worker.generation.engine.select_exemplars", new_callable=AsyncMock, return_value=[])
    @patch("worker.generation.engine.detect_vertical", return_value="depin")
    async def test_partial_failure_continues(
        self, _mock_vertical: MagicMock, _mock_exemplars: AsyncMock
    ) -> None:
        """If one platform's LLM call fails, other platforms still generate."""
        call_count = 0

        async def _generate_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Fail on the first call
            if call_count == 1:
                raise LLMGenerationError("Provider down")
            return _make_llm_response()

        topic = _make_topic(thesis="Test thesis")
        session = AsyncMock()
        llm_client = AsyncMock()
        llm_client.generate = AsyncMock(side_effect=_generate_side_effect)

        drafts = await generate_for_topic(topic, session, llm_client)

        # One platform failed, so we should have 3 drafts
        assert len(drafts) == 3
        # A system alert should have been added
        session.add.assert_called()
        # Topic should still be marked as GENERATED
        assert topic.status == TopicStatus.GENERATED

    @pytest.mark.asyncio
    @patch("worker.generation.engine.select_exemplars", new_callable=AsyncMock, return_value=[])
    @patch("worker.generation.engine.detect_vertical", return_value="sports_seahawks")
    async def test_sets_topic_vertical(
        self, _mock_vertical: MagicMock, _mock_exemplars: AsyncMock
    ) -> None:
        """Verify topic.vertical is set after generation."""
        topic = _make_topic(thesis="Seahawks draft analysis")
        session = AsyncMock()
        llm_client = AsyncMock()
        llm_client.generate = AsyncMock(return_value=_make_llm_response())

        await generate_for_topic(topic, session, llm_client)

        assert topic.vertical == "sports_seahawks"
