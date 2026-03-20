"""Tests for vertical-aware voice exemplar selection."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.generation.exemplar_selector import select_exemplars


def _make_exemplar(vertical: str = "general", platform: str = "substack") -> MagicMock:
    ex = MagicMock()
    ex.id = uuid.uuid4()
    ex.content = f"Exemplar content for {vertical}"
    ex.platform = platform
    ex.vertical = vertical
    ex.active = True
    return ex


class TestSelectExemplars:
    @pytest.mark.asyncio
    async def test_selects_matching_vertical(self):
        exemplars = [_make_exemplar("sports_seahawks") for _ in range(5)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = exemplars
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await select_exemplars(session, "substack", "sports_seahawks")
        assert 3 <= len(result) <= 5
        for ex in result:
            assert ex.vertical == "sports_seahawks"

    @pytest.mark.asyncio
    async def test_fills_from_other_verticals(self):
        matching = [_make_exemplar("depin")]
        others = [_make_exemplar("ai_politics") for _ in range(4)]
        all_exemplars = matching + others

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = all_exemplars
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await select_exemplars(session, "substack", "depin")
        assert len(result) >= 3
        assert any(ex.vertical == "depin" for ex in result)

    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(self):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await select_exemplars(session, "substack", "general")
        assert result == []

    @pytest.mark.asyncio
    async def test_max_5_exemplars(self):
        exemplars = [_make_exemplar("ai_politics") for _ in range(10)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = exemplars
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await select_exemplars(session, "substack", "ai_politics")
        assert len(result) <= 5
