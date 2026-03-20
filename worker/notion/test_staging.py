"""Tests for Notion draft staging."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.notion.staging import stage_drafts
from worker.notion.client import NotionWriteError


def _make_draft(notion_page_id=None):
    draft = MagicMock()
    draft.id = uuid.uuid4()
    draft.topic_id = uuid.uuid4()
    draft.platform = MagicMock(value="substack")
    draft.content = "Generated article content"
    draft.status = MagicMock(value="draft")
    draft.notion_page_id = notion_page_id
    draft.model_used = "groq/llama-3.3-70b-versatile"
    draft.token_cost = 0.001
    draft.generation_metadata = {}
    draft.generated_at = None

    topic = MagicMock()
    topic.id = draft.topic_id
    topic.thesis_provided = True
    topic.scored_signal = MagicMock()
    topic.scored_signal.composite_score = 75.0
    topic.scored_signal.score_breakdown = {"signal_strength": 80}
    topic.scored_signal.signal = MagicMock()
    topic.scored_signal.signal.title = "Test Topic"
    draft.topic = topic

    return draft


class TestStageDrafts:
    @pytest.mark.asyncio
    async def test_creates_notion_page_and_stores_id(self):
        draft = _make_draft()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [draft]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.create_page = AsyncMock(return_value="page-abc")
        mock_client.add_comment = AsyncMock()

        counts = await stage_drafts(session, mock_client)

        assert counts["staged"] == 1
        assert draft.notion_page_id == "page-abc"
        mock_client.create_page.assert_called_once()
        mock_client.add_comment.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_already_staged(self):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        counts = await stage_drafts(session, mock_client)

        assert counts == {"staged": 0, "errors": 0}
        mock_client.create_page.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_failure_creates_alert(self):
        draft1 = _make_draft()
        draft2 = _make_draft()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [draft1, draft2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)
        # session.add is synchronous in SQLAlchemy; use a plain MagicMock so the
        # test doesn't emit "coroutine never awaited" warnings.
        session.add = MagicMock()

        mock_client = AsyncMock()
        mock_client.create_page = AsyncMock(
            side_effect=["page-1", NotionWriteError("Notion API error")]
        )
        mock_client.add_comment = AsyncMock()

        counts = await stage_drafts(session, mock_client)

        assert counts["staged"] == 1
        assert counts["errors"] == 1
        assert draft1.notion_page_id == "page-1"
        assert draft2.notion_page_id is None
        assert session.add.called
