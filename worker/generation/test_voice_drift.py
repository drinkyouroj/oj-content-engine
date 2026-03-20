"""Tests for Substack voice-drift self-critique."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from worker.generation.voice_drift import run_voice_critique
from worker.generation.llm_client import LLMResponse, LLMGenerationError


class TestVoiceCritique:
    @pytest.mark.asyncio
    async def test_returns_revised_draft(self):
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="Revised draft without generic language",
            total_tokens=800,
            model="llama-3.3-70b-versatile",
            provider="groq",
        ))

        result = await run_voice_critique(
            draft="Original draft with some generic language",
            llm_client=mock_client,
            provider="groq",
            model="llama-3.3-70b-versatile",
        )

        assert result.content == "Revised draft without generic language"
        assert result.total_tokens == 800
        mock_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_critique_prompt_contains_brand_voice(self):
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="Revised", total_tokens=100, model="test", provider="groq",
        ))

        await run_voice_critique(
            draft="Some draft",
            llm_client=mock_client,
            provider="groq",
            model="test",
        )

        call_kwargs = mock_client.generate.call_args.kwargs
        assert "drinkYourOJ" in call_kwargs["system_prompt"]
        assert "em dashes" in call_kwargs["system_prompt"]
        assert "Some draft" in call_kwargs["user_prompt"]

    @pytest.mark.asyncio
    async def test_llm_failure_propagates(self):
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(side_effect=LLMGenerationError("API down"))

        with pytest.raises(LLMGenerationError):
            await run_voice_critique(
                draft="Some draft",
                llm_client=mock_client,
                provider="groq",
                model="test",
            )
