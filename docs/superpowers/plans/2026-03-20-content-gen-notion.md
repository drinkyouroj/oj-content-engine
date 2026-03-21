# Content Generation + Notion Staging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the content generation engine that converts triaged topics into platform-specific drafts (Substack, Twitter, LinkedIn, Instagram) and stages them in Notion for review.

**Architecture:** Three-layer prompt system (system prompt + context injection + generation prompt) with configurable LLM provider (Groq default, Anthropic upgrade path). Voice exemplars selected by vertical similarity. Substack gets a voice-drift self-critique second pass. Notion staging writes drafts to the Second Brain database with rate-limited batching.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x async, Groq SDK, Anthropic SDK, notion-client, beautifulsoup4, httpx, pytest + respx

**Spec:** `docs/superpowers/specs/2026-03-20-content-gen-notion-design.md`

**Branch:** `feature/content-gen` (from `develop`)

**Existing patterns to follow:**
- Models: `worker/app/models/*.py` (UUIDPrimaryKey + TimestampMixin + values_callable on enums)
- Migrations: `worker/alembic/versions/001_initial_schema.py` (raw SQL via separate `op.execute()`)
- LLM calls: `worker/scoring/pass2.py` (Groq client, retry with backoff, JSON parsing, code fence stripping)
- ARQ jobs: `worker/jobs/triage_jobs.py` (session creation, try/finally cleanup)
- Tests: `worker/triage/test_engine.py` (MagicMock + AsyncMock, no real DB/network)

---

### Task 1: Alembic Migrations

**Files:**
- Create: `worker/alembic/versions/002_add_exemplar_vertical.py`
- Create: `worker/alembic/versions/003_add_draft_metadata_and_topic_vertical.py`

- [ ] **Step 1: Write migration 002 — add vertical to voice_exemplars**

```python
"""add vertical column to voice_exemplars

Revision ID: 002
Revises: 001
Create Date: 2026-03-20
"""
from __future__ import annotations

from alembic import op

revision: str = "002"
down_revision: str = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE voice_exemplars ADD COLUMN vertical VARCHAR(50) DEFAULT 'general'")


def downgrade() -> None:
    op.execute("ALTER TABLE voice_exemplars DROP COLUMN vertical")
```

- [ ] **Step 2: Write migration 003 — add generation_metadata and topic vertical**

```python
"""add generation_metadata to content_drafts and vertical to topics

Revision ID: 003
Revises: 002
Create Date: 2026-03-20
"""
from __future__ import annotations

from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE content_drafts ADD COLUMN generation_metadata JSONB DEFAULT '{}'")
    op.execute("ALTER TABLE topics ADD COLUMN vertical VARCHAR(50)")


def downgrade() -> None:
    op.execute("ALTER TABLE content_drafts DROP COLUMN generation_metadata")
    op.execute("ALTER TABLE topics DROP COLUMN vertical")
```

- [ ] **Step 3: Update ORM models to match migrations**

Add to `worker/app/models/voice_exemplar.py`:
```python
vertical: Mapped[str] = mapped_column(Text, default="general", server_default="general", nullable=False)
```

Add to `worker/app/models/topic.py`:
```python
vertical: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Add to `worker/app/models/content_draft.py`:
```python
from sqlalchemy.dialects.postgresql import JSONB

generation_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
```

- [ ] **Step 4: Run migrations against Neon**

```bash
cd worker && python3.12 -m alembic upgrade head
```

Expected: 2 migrations applied successfully.

- [ ] **Step 5: Commit**

```bash
git add worker/alembic/versions/002_add_exemplar_vertical.py worker/alembic/versions/003_add_draft_metadata_and_topic_vertical.py worker/app/models/voice_exemplar.py worker/app/models/topic.py worker/app/models/content_draft.py
git commit -m "feat(db): add vertical, generation_metadata columns for content gen"
```

---

### Task 2: Vertical Detection Module

**Files:**
- Create: `worker/generation/__init__.py`
- Create: `worker/generation/verticals.py`
- Create: `worker/generation/test_verticals.py`

- [ ] **Step 1: Create package init**

```python
# worker/generation/__init__.py
"""Content generation engine — converts triaged topics into platform-specific drafts."""
```

- [ ] **Step 2: Write failing tests for vertical detection**

```python
# worker/generation/test_verticals.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd worker && python3.12 -m pytest generation/test_verticals.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'worker.generation.verticals'`

- [ ] **Step 4: Implement vertical detection**

```python
# worker/generation/verticals.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd worker && python3.12 -m pytest generation/test_verticals.py -v
```

Expected: All 9 tests pass.

- [ ] **Step 6: Commit**

```bash
git add worker/generation/
git commit -m "feat(generation): add vertical detection for topic classification"
```

---

### Task 3: LLM Client Abstraction

**Files:**
- Create: `worker/generation/llm_client.py`
- Create: `worker/generation/test_llm_client.py`

- [ ] **Step 1: Write failing tests**

```python
# worker/generation/test_llm_client.py
"""Tests for the LLM client provider abstraction."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.generation.llm_client import (
    LLMClient,
    LLMGenerationError,
    GENERATION_MODELS,
    get_model_config,
)


class TestGetModelConfig:
    def test_returns_default_config(self):
        config = get_model_config("substack")
        assert config["provider"] in ("groq", "anthropic")
        assert "model" in config

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("GENERATION_MODEL_SUBSTACK", "anthropic/claude-sonnet-4-5")
        config = get_model_config("substack")
        assert config["provider"] == "anthropic"
        assert config["model"] == "claude-sonnet-4-5"

    def test_substack_critique_key_exists(self):
        assert "substack_critique" in GENERATION_MODELS

    def test_unknown_platform_raises(self):
        with pytest.raises(KeyError):
            get_model_config("tiktok")


class TestLLMClient:
    @pytest.mark.asyncio
    async def test_generate_groq(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated content here"
        mock_response.usage = MagicMock(total_tokens=500)

        with patch("worker.generation.llm_client.AsyncGroq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_response)

            client = LLMClient(groq_api_key="test-key")
            result = await client.generate(
                system_prompt="You are a writer",
                user_prompt="Write something",
                provider="groq",
                model="llama-3.3-70b-versatile",
            )

            assert result.content == "Generated content here"
            assert result.total_tokens == 500

    @pytest.mark.asyncio
    async def test_generate_anthropic(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Anthropic output")]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=400)

        with patch("worker.generation.llm_client.AsyncAnthropic") as MockAnthropic:
            instance = MockAnthropic.return_value
            instance.messages.create = AsyncMock(return_value=mock_response)

            client = LLMClient(anthropic_api_key="test-key")
            result = await client.generate(
                system_prompt="You are a writer",
                user_prompt="Write something",
                provider="anthropic",
                model="claude-sonnet-4-5",
            )

            assert result.content == "Anthropic output"
            assert result.total_tokens == 500

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        with patch("worker.generation.llm_client.AsyncGroq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create = AsyncMock(
                side_effect=[Exception("API error"), Exception("API error again")]
            )

            client = LLMClient(groq_api_key="test-key")
            with pytest.raises(LLMGenerationError):
                await client.generate(
                    system_prompt="test",
                    user_prompt="test",
                    provider="groq",
                    model="llama-3.3-70b-versatile",
                    max_retries=2,
                )

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self):
        client = LLMClient()
        with pytest.raises(LLMGenerationError, match="API key"):
            await client.generate(
                system_prompt="test",
                user_prompt="test",
                provider="groq",
                model="test",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd worker && python3.12 -m pytest generation/test_llm_client.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement LLM client**

```python
# worker/generation/llm_client.py
"""LLM client abstraction — wraps Groq and Anthropic providers.

Provides a unified interface for content generation across providers.
Handles retries, code fence stripping, and token tracking.
Provider and model are configurable per platform via GENERATION_MODELS
dict or environment variable overrides.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from groq import AsyncGroq

logger = logging.getLogger(__name__)


class LLMGenerationError(Exception):
    """Raised when LLM generation fails after all retries."""


@dataclass
class LLMResponse:
    """Structured response from an LLM generation call.

    Attributes:
        content: The generated text.
        total_tokens: Total tokens used (input + output).
        model: Model identifier used for generation.
        provider: Provider name (groq or anthropic).
    """
    content: str
    total_tokens: int
    model: str
    provider: str


GENERATION_MODELS: dict[str, dict[str, str]] = {
    "substack": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    "twitter": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    "linkedin": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    "instagram": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    "substack_critique": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
}


def get_model_config(platform: str) -> dict[str, str]:
    """Get model config for a platform, with env var override.

    Environment variable format: GENERATION_MODEL_<PLATFORM>=provider/model
    Example: GENERATION_MODEL_SUBSTACK=anthropic/claude-sonnet-4-5

    Args:
        platform: Platform key (substack, twitter, linkedin, instagram, substack_critique).

    Returns:
        Dict with 'provider' and 'model' keys.

    Raises:
        KeyError: If platform is not in GENERATION_MODELS and no env override.
    """
    env_key = f"GENERATION_MODEL_{platform.upper()}"
    env_val = os.environ.get(env_key)

    if env_val and "/" in env_val:
        provider, model = env_val.split("/", 1)
        return {"provider": provider, "model": model}

    return dict(GENERATION_MODELS[platform])


class LLMClient:
    """Unified LLM client for Groq and Anthropic providers.

    Args:
        groq_api_key: Groq API key (required for Groq provider).
        anthropic_api_key: Anthropic API key (required for Anthropic provider).
    """

    def __init__(
        self,
        groq_api_key: str = "",
        anthropic_api_key: str = "",
    ) -> None:
        self._groq_key = groq_api_key
        self._anthropic_key = anthropic_api_key

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Generate text using the specified provider and model.

        Args:
            system_prompt: System-level instructions.
            user_prompt: User-level prompt with context and task.
            provider: Provider name ('groq' or 'anthropic').
            model: Model identifier string.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            max_retries: Number of retry attempts on failure.

        Returns:
            LLMResponse with generated content and metadata.

        Raises:
            LLMGenerationError: If all retry attempts fail or API key missing.
        """
        if provider == "groq":
            return await self._generate_groq(
                system_prompt, user_prompt, model, max_tokens, temperature, max_retries
            )
        elif provider == "anthropic":
            return await self._generate_anthropic(
                system_prompt, user_prompt, model, max_tokens, temperature, max_retries
            )
        else:
            raise LLMGenerationError(f"Unknown provider: {provider}")

    async def _generate_groq(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        max_retries: int,
    ) -> LLMResponse:
        if not self._groq_key:
            raise LLMGenerationError("Groq API key not configured")

        client = AsyncGroq(api_key=self._groq_key)
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                content = response.choices[0].message.content.strip()
                content = _strip_code_fences(content)
                total_tokens = getattr(response.usage, "total_tokens", 0)

                return LLMResponse(
                    content=content,
                    total_tokens=total_tokens,
                    model=model,
                    provider="groq",
                )
            except Exception as exc:
                last_error = exc
                wait = 2 ** attempt
                logger.warning(
                    "Groq generation attempt %d/%d failed: %s. Retrying in %ds.",
                    attempt + 1, max_retries, exc, wait,
                )
                await asyncio.sleep(wait)

        raise LLMGenerationError(
            f"Groq generation failed after {max_retries} retries: {last_error}"
        ) from last_error

    async def _generate_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        max_retries: int,
    ) -> LLMResponse:
        if not self._anthropic_key:
            raise LLMGenerationError("Anthropic API key not configured")

        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self._anthropic_key)
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                content = response.content[0].text.strip()
                content = _strip_code_fences(content)
                total_tokens = response.usage.input_tokens + response.usage.output_tokens

                return LLMResponse(
                    content=content,
                    total_tokens=total_tokens,
                    model=model,
                    provider="anthropic",
                )
            except Exception as exc:
                last_error = exc
                wait = 2 ** attempt
                logger.warning(
                    "Anthropic generation attempt %d/%d failed: %s. Retrying in %ds.",
                    attempt + 1, max_retries, exc, wait,
                )
                await asyncio.sleep(wait)

        raise LLMGenerationError(
            f"Anthropic generation failed after {max_retries} retries: {last_error}"
        ) from last_error


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM output if present."""
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
        text = text.strip()
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd worker && python3.12 -m pytest generation/test_llm_client.py -v
```

Expected: All 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add worker/generation/llm_client.py worker/generation/test_llm_client.py
git commit -m "feat(generation): add LLM client abstraction for Groq and Anthropic"
```

---

### Task 4: Exemplar Selection

**Files:**
- Create: `worker/generation/exemplar_selector.py`
- Create: `worker/generation/test_exemplar_selector.py`

- [ ] **Step 1: Write failing tests**

```python
# worker/generation/test_exemplar_selector.py
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
        """When < 3 matches, fills remaining slots from other verticals."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd worker && python3.12 -m pytest generation/test_exemplar_selector.py -v
```

- [ ] **Step 3: Implement exemplar selector**

```python
# worker/generation/exemplar_selector.py
"""Vertical-aware voice exemplar selection.

Selects 3-5 voice exemplars from the database, prioritizing exemplars
whose vertical matches the topic's detected vertical. Falls back to
other verticals if insufficient matches.
"""
from __future__ import annotations

import logging
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.voice_exemplar import VoiceExemplar

logger = logging.getLogger(__name__)

_MIN_EXEMPLARS = 3
_MAX_EXEMPLARS = 5


async def select_exemplars(
    session: AsyncSession,
    platform: str,
    vertical: str,
) -> list[VoiceExemplar]:
    """Select 3-5 voice exemplars prioritized by vertical match.

    Selection logic:
    1. Query all active exemplars for the target platform.
    2. Split into matching-vertical and other-vertical groups.
    3. If >= 3 matches, randomly select 3-5 from matches.
    4. If < 3 matches, take all matches + fill from others.
    5. If zero total, return empty list.

    Args:
        session: Async database session.
        platform: Target platform (substack, twitter, etc.).
        vertical: Topic's detected vertical.

    Returns:
        List of VoiceExemplar instances (0 to 5).
    """
    stmt = select(VoiceExemplar).where(
        VoiceExemplar.active == True,  # noqa: E712
        VoiceExemplar.platform == platform,
    )
    result = await session.execute(stmt)
    all_exemplars = result.scalars().all()

    if not all_exemplars:
        logger.info("No active exemplars found for platform=%s", platform)
        return []

    matching = [e for e in all_exemplars if e.vertical == vertical]
    others = [e for e in all_exemplars if e.vertical != vertical]

    if len(matching) >= _MIN_EXEMPLARS:
        count = random.randint(_MIN_EXEMPLARS, min(_MAX_EXEMPLARS, len(matching)))
        selected = random.sample(matching, count)
    else:
        selected = list(matching)
        remaining = _MIN_EXEMPLARS - len(selected)
        if others and remaining > 0:
            fill_count = min(remaining, len(others))
            selected.extend(random.sample(others, fill_count))

    logger.info(
        "Selected %d exemplars (vertical=%s, matched=%d, filled=%d)",
        len(selected), vertical, len(matching), max(0, len(selected) - len(matching)),
    )
    return selected
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd worker && python3.12 -m pytest generation/test_exemplar_selector.py -v
```

- [ ] **Step 5: Commit**

```bash
git add worker/generation/exemplar_selector.py worker/generation/test_exemplar_selector.py
git commit -m "feat(generation): add vertical-aware voice exemplar selection"
```

---

### Task 5: Platform Prompt Templates

**Files:**
- Create: `worker/generation/prompts/__init__.py`
- Create: `worker/generation/prompts/system.py`
- Create: `worker/generation/prompts/substack.py`
- Create: `worker/generation/prompts/twitter.py`
- Create: `worker/generation/prompts/linkedin.py`
- Create: `worker/generation/prompts/instagram.py`

This task is prompt engineering — no TDD needed. The prompts are static text with variable injection points. Tests in Task 7 (engine) will validate prompt assembly.

- [ ] **Step 1: Create prompts package and system prompt**

`worker/generation/prompts/__init__.py`:
```python
"""Platform-specific prompt templates for content generation."""
```

`worker/generation/prompts/system.py` — Brand voice bible, hard-no list, personal context. This is the system prompt shared across all platforms. Contains:
- Brand voice description (intellectual stand-up comedy, dry, direct, systems-thinker)
- Hard bans list (em dashes, banned words, passive voice)
- Personal integration context (Seattle→Michigan, sysadmin background, web3 burnout)
- Voice rules (vary sentence beginnings, active voice, concrete metaphors)

- [ ] **Step 2: Create Substack prompt**

`worker/generation/prompts/substack.py` — Template-based (Triple Connection, System Audit, Concept Decoder, Pattern Report), 1500-1600 words, title/subtitle rules, image markers, footnoted sources, section thesis sentences.

- [ ] **Step 3: Create Twitter prompt**

`worker/generation/prompts/twitter.py` — 5-12 tweets, 280 char limit, hook→substance→CTA, thread format.

- [ ] **Step 4: Create LinkedIn prompt**

`worker/generation/prompts/linkedin.py` — 300-600 words, hook→3 insights→closing, honest not hustle-porn.

- [ ] **Step 5: Create Instagram prompt**

`worker/generation/prompts/instagram.py` — 150-word caption + image card prompt, visual-first.

Each prompt module exports a `build_prompt(topic_title, topic_body, score_breakdown, thesis, exemplars)` function that returns the assembled user prompt string.

- [ ] **Step 6: Write basic prompt tests**

Create `worker/generation/prompts/test_prompts.py`:

```python
"""Snapshot tests for prompt template assembly."""
from __future__ import annotations

import pytest

from worker.generation.prompts.substack import build_prompt as build_substack
from worker.generation.prompts.twitter import build_prompt as build_twitter
from worker.generation.prompts.linkedin import build_prompt as build_linkedin
from worker.generation.prompts.instagram import build_prompt as build_instagram


_SCORE_BREAKDOWN = {
    "signal_strength": 80, "timing_window": 70, "depth_potential": 75,
    "novelty": 65, "community_resonance": 60, "brand_angle_availability": 80,
}


class TestPromptAssembly:
    def test_substack_contains_topic_title(self):
        prompt = build_substack("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, "My thesis", [])
        assert "AI Safety Theater" in prompt
        assert "My thesis" in prompt

    def test_substack_without_thesis(self):
        prompt = build_substack("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, None, [])
        assert "AI Safety Theater" in prompt
        assert "AI-originated" in prompt or "no thesis" in prompt.lower()

    def test_twitter_contains_tweet_constraints(self):
        prompt = build_twitter("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, None, [])
        assert "280" in prompt  # Character limit
        assert "AI Safety Theater" in prompt

    def test_linkedin_contains_topic(self):
        prompt = build_linkedin("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, None, [])
        assert "AI Safety Theater" in prompt

    def test_instagram_contains_topic(self):
        prompt = build_instagram("AI Safety Theater", "Preview text", _SCORE_BREAKDOWN, None, [])
        assert "AI Safety Theater" in prompt

    def test_exemplars_injected(self):
        exemplars = ["Example post about DePIN infrastructure"]
        prompt = build_substack("Test Topic", "Body", _SCORE_BREAKDOWN, None, exemplars)
        assert "DePIN infrastructure" in prompt
```

- [ ] **Step 7: Run prompt tests**

```bash
cd worker && python3.12 -m pytest generation/prompts/test_prompts.py -v
```

- [ ] **Step 8: Commit**

```bash
git add worker/generation/prompts/
git commit -m "feat(generation): add platform-specific prompt templates with tests"
```

---

### Task 6: Voice-Drift Critique

**Files:**
- Create: `worker/generation/voice_drift.py`
- Create: `worker/generation/test_voice_drift.py`

- [ ] **Step 1: Write failing tests**

```python
# worker/generation/test_voice_drift.py
"""Tests for Substack voice-drift self-critique."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd worker && python3.12 -m pytest generation/test_voice_drift.py -v
```

- [ ] **Step 3: Implement voice-drift critique**

```python
# worker/generation/voice_drift.py
"""Substack voice-drift self-critique — dedicated second pass.

Reads a generated Substack draft and flags sentences that sound generic,
off-brand, or like a press release. Rewrites flagged sentences in
Justin's voice. Returns the revised draft.

Only used for Substack long-form. Other platforms skip this.
"""
from __future__ import annotations

import logging

from worker.generation.llm_client import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

_CRITIQUE_SYSTEM_PROMPT = """\
You are a drinkYourOJ subscriber who has read every post since 2023. You know \
Justin's voice intimately: dry, direct, systems-thinking, occasionally funny, \
never breathless.

Your job is to review a draft article and produce a REVISED version. \
Do NOT output commentary or analysis. Output ONLY the full revised article.

For every sentence that sounds like it could appear in a generic tech newsletter, \
a press release, or a crypto hype blog, rewrite it in Justin's voice.

Self-review checklist — fix all violations silently:
- No em dashes (—)
- No banned words: delve, tapestry, vibrant, landscape, realm, embark, moreover, \
notably, pivotal, arguably
- No banned phrases: "Everyone wants to", "Without further ado", "Have you ever wondered", \
"Picture this"
- No excessive parallelism: "It's not about X, it's about Y"
- No passive constructions that hide the actor
- Sentence beginnings must vary (prepositional phrases, rhetorical questions, \
adverbs, one-word beats)
- Every abstract concept needs a concrete metaphor
- Active voice; name the actor
- Technical terms defined before use
- No concept explained twice
- Ending: thought-provoking question OR clear point, not both

Output the full revised article in markdown format. Nothing else.\
"""


async def run_voice_critique(
    draft: str,
    llm_client: LLMClient,
    provider: str,
    model: str,
) -> LLMResponse:
    """Run voice-drift self-critique on a Substack draft.

    Args:
        draft: The generated Substack article text.
        llm_client: LLMClient instance.
        provider: Provider name for the critique model.
        model: Model identifier for the critique.

    Returns:
        LLMResponse with revised draft content.

    Raises:
        LLMGenerationError: If the critique LLM call fails.
    """
    logger.info("Running voice-drift critique (%s/%s)", provider, model)

    return await llm_client.generate(
        system_prompt=_CRITIQUE_SYSTEM_PROMPT,
        user_prompt=f"Review and revise this draft:\n\n{draft}",
        provider=provider,
        model=model,
        max_tokens=8192,
        temperature=0.5,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd worker && python3.12 -m pytest generation/test_voice_drift.py -v
```

- [ ] **Step 5: Commit**

```bash
git add worker/generation/voice_drift.py worker/generation/test_voice_drift.py
git commit -m "feat(generation): add Substack voice-drift self-critique"
```

---

### Task 7: Generation Engine

**Files:**
- Create: `worker/generation/engine.py`
- Create: `worker/generation/test_engine.py`

This is the orchestrator that ties everything together: vertical detection → exemplar selection → prompt assembly → LLM generation → voice-drift critique (Substack) → ContentDraft persistence.

- [ ] **Step 1: Write failing tests**

```python
# worker/generation/test_engine.py
"""Tests for the content generation engine orchestrator."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

from worker.app.models.content_draft import Platform, DraftStatus
from worker.app.models.topic import TopicStatus
from worker.generation.engine import generate_for_topic
from worker.generation.llm_client import LLMResponse


def _make_topic(
    thesis: str | None = None,
    composite_score: float = 70.0,
) -> MagicMock:
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


class TestGenerateForTopic:
    @pytest.mark.asyncio
    async def test_generates_4_platform_drafts(self):
        topic = _make_topic(thesis="AI safety is theater")
        session = AsyncMock()
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="Generated content",
            total_tokens=500,
            model="llama-3.3-70b-versatile",
            provider="groq",
        ))

        with patch("worker.generation.engine.select_exemplars", return_value=[]):
            drafts = await generate_for_topic(topic, session, mock_client)

        assert len(drafts) == 4
        platforms = {d.platform for d in drafts}
        assert platforms == {Platform.SUBSTACK, Platform.TWITTER, Platform.LINKEDIN, Platform.INSTAGRAM}

    @pytest.mark.asyncio
    async def test_substack_gets_voice_critique(self):
        topic = _make_topic()
        session = AsyncMock()
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="Generated content",
            total_tokens=500,
            model="test",
            provider="groq",
        ))

        with patch("worker.generation.engine.select_exemplars", return_value=[]):
            with patch("worker.generation.engine.run_voice_critique") as mock_critique:
                mock_critique.return_value = LLMResponse(
                    content="Revised content",
                    total_tokens=800,
                    model="test",
                    provider="groq",
                )
                drafts = await generate_for_topic(topic, session, mock_client)

        mock_critique.assert_called_once()
        substack_draft = [d for d in drafts if d.platform == Platform.SUBSTACK][0]
        assert substack_draft.content == "Revised content"

    @pytest.mark.asyncio
    async def test_no_thesis_sets_ai_originated_flag(self):
        topic = _make_topic(thesis=None)
        session = AsyncMock()
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="Content", total_tokens=100, model="test", provider="groq",
        ))

        with patch("worker.generation.engine.select_exemplars", return_value=[]):
            with patch("worker.generation.engine.run_voice_critique", return_value=LLMResponse(
                content="Revised", total_tokens=100, model="test", provider="groq",
            )):
                drafts = await generate_for_topic(topic, session, mock_client)

        for draft in drafts:
            assert draft.generation_metadata.get("ai_originated") is True

    @pytest.mark.asyncio
    async def test_partial_failure_continues(self):
        """If one platform fails, others still generate."""
        topic = _make_topic()
        session = AsyncMock()
        mock_client = AsyncMock()

        call_count = 0
        async def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Fail on 2nd platform
                from worker.generation.llm_client import LLMGenerationError
                raise LLMGenerationError("API error")
            return LLMResponse(content="Content", total_tokens=100, model="test", provider="groq")

        mock_client.generate = AsyncMock(side_effect=side_effect)

        with patch("worker.generation.engine.select_exemplars", return_value=[]):
            with patch("worker.generation.engine.run_voice_critique", return_value=LLMResponse(
                content="Revised", total_tokens=100, model="test", provider="groq",
            )):
                drafts = await generate_for_topic(topic, session, mock_client)

        assert len(drafts) == 3  # 4 platforms - 1 failure

    @pytest.mark.asyncio
    async def test_sets_topic_vertical(self):
        topic = _make_topic()
        session = AsyncMock()
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="Content", total_tokens=100, model="test", provider="groq",
        ))

        with patch("worker.generation.engine.select_exemplars", return_value=[]):
            with patch("worker.generation.engine.run_voice_critique", return_value=LLMResponse(
                content="Revised", total_tokens=100, model="test", provider="groq",
            )):
                await generate_for_topic(topic, session, mock_client)

        assert topic.vertical is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd worker && python3.12 -m pytest generation/test_engine.py -v
```

- [ ] **Step 3: Implement generation engine**

The engine:
1. Detects topic vertical, stores on `topic.vertical`
2. Selects exemplars
3. Loops through platforms, assembling prompts and calling LLM
4. Runs voice-drift critique for Substack
5. Creates ContentDraft rows
6. Returns list of created drafts

Key implementation details:
- Each platform is wrapped in try/except — failure skips that platform, logs error, creates system_alert
- ContentDraft.generation_metadata tracks: ai_originated, no_exemplars_available, voice_drift_applied, prompt_version
- Topic.status updated to GENERATING before loop, GENERATED after
- Token costs estimated from total_tokens and provider pricing

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd worker && python3.12 -m pytest generation/test_engine.py -v
```

- [ ] **Step 5: Commit**

```bash
git add worker/generation/engine.py worker/generation/test_engine.py
git commit -m "feat(generation): add content generation engine orchestrator"
```

---

### Task 8: Notion Client

**Files:**
- Create: `worker/notion/__init__.py`
- Create: `worker/notion/client.py`
- Create: `worker/notion/test_client.py`

- [ ] **Step 1: Create package init**

```python
# worker/notion/__init__.py
"""Notion API integration — staging drafts for review."""
```

- [ ] **Step 2: Write failing tests**

```python
# worker/notion/test_client.py
"""Tests for the Notion API client wrapper."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

from worker.notion.client import NotionClient, NotionWriteError


class TestNotionClient:
    def test_init_requires_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            NotionClient(api_key="", database_id="test-db")

    def test_init_requires_database_id(self):
        with pytest.raises(ValueError, match="database_id"):
            NotionClient(api_key="test-key", database_id="")

    @pytest.mark.asyncio
    async def test_create_page_returns_page_id(self):
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "page-123"}

        with patch("worker.notion.client.AsyncClient", return_value=mock_notion):
            client = NotionClient(api_key="test-key", database_id="test-db")
            page_id = await client.create_page(
                title="[Substack] Test Article",
                platform="substack",
                content="Article body here",
                properties={
                    "composite_score": 75.0,
                    "thesis_provided": True,
                    "model_used": "groq/llama-3.3-70b-versatile",
                },
            )

        assert page_id == "page-123"

    @pytest.mark.asyncio
    async def test_add_comment(self):
        mock_notion = MagicMock()
        mock_notion.comments.create.return_value = {"id": "comment-456"}

        with patch("worker.notion.client.AsyncClient", return_value=mock_notion):
            client = NotionClient(api_key="test-key", database_id="test-db")
            await client.add_comment("page-123", "Generation metadata here")

        mock_notion.comments.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limiting_delay(self):
        """Verify 400ms delay between API calls."""
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "page-1"}

        with patch("worker.notion.client.AsyncClient", return_value=mock_notion):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                client = NotionClient(api_key="test-key", database_id="test-db")
                await client.create_page(
                    title="Test", platform="substack",
                    content="Body", properties={},
                )

                mock_sleep.assert_called_with(0.4)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd worker && python3.12 -m pytest notion/test_client.py -v
```

- [ ] **Step 4: Implement Notion client**

The client wraps the `notion-client` SDK with:
- Rate limiting (400ms delay between API calls)
- Page creation with all properties from spec Section 3
- Comment creation for generation metadata
- Error wrapping as `NotionWriteError`

Note: The `notion-client` package's `AsyncClient` may need to be used synchronously wrapped in `asyncio.to_thread()` if it doesn't support async natively. Check the package docs during implementation.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd worker && python3.12 -m pytest notion/test_client.py -v
```

- [ ] **Step 6: Commit**

```bash
git add worker/notion/
git commit -m "feat(notion): add rate-limited Notion API client"
```

---

### Task 9: Notion Staging

**Files:**
- Create: `worker/notion/staging.py`
- Create: `worker/notion/test_staging.py`

- [ ] **Step 1: Write failing tests**

```python
# worker/notion/test_staging.py
"""Tests for Notion draft staging."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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
        """Drafts with existing notion_page_id are not re-staged."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []  # Query filters out already-staged
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
        # system_alert should be created
        assert session.add.called
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd worker && python3.12 -m pytest notion/test_staging.py -v
```

- [ ] **Step 3: Implement staging logic**

`stage_drafts()` loops through ContentDraft rows with `notion_page_id IS NULL`:
1. Build Notion page properties from ContentDraft + Topic + ScoredSignal
2. Create page via NotionClient
3. Add metadata comment
4. Store page_id back on ContentDraft row
5. On failure: create SystemAlert, continue to next draft

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd worker && python3.12 -m pytest notion/test_staging.py -v
```

- [ ] **Step 5: Commit**

```bash
git add worker/notion/staging.py worker/notion/test_staging.py
git commit -m "feat(notion): add draft staging with bidirectional linking"
```

---

### Task 10: ARQ Jobs + Worker Registration

**Files:**
- Create: `worker/jobs/generation_jobs.py`
- Create: `worker/jobs/notion_jobs.py`
- Modify: `worker/jobs/worker.py`
- Modify: `worker/pyproject.toml`
- Modify: `worker/conftest.py`

- [ ] **Step 1: Create generation ARQ job**

```python
# worker/jobs/generation_jobs.py
"""ARQ job for content generation.

Wraps the generation engine in an ARQ-compatible async function.
Processes all queued topics, generates 4 platform drafts per topic,
then triggers Notion staging.

Implements PRD Section 4 (Content Generation Pipeline).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory
from worker.app.models.scored_signal import ScoredSignal
from worker.app.models.topic import Topic, TopicStatus
from worker.generation.engine import generate_for_topic
from worker.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


async def _get_session() -> tuple[AsyncSession, AsyncEngine]:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    session = session_factory()
    return session, engine


async def run_generation_job(ctx: dict) -> dict[str, int]:
    """ARQ job: generate content drafts for all queued topics.

    Queries topics with status='queued' (auto-approved) or status='review'
    with a thesis provided (manually approved), generates 4 platform
    drafts for each, then calls Notion staging.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Dictionary with counts: {"topics_processed": N, "drafts_created": N, "errors": N}.

    Estimated runtime: 30-120s per topic (4 LLM calls + 1 critique).
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Per-topic errors logged; does not block other topics.
    """
    from worker.jobs.notion_jobs import run_notion_staging_job

    settings = get_settings()
    session, engine = await _get_session()

    try:
        # Queued topics (auto-approved, score >= 65) or review topics with thesis (manually approved)
        stmt = select(Topic).where(
            (Topic.status == TopicStatus.QUEUED)
            | ((Topic.status == TopicStatus.REVIEW) & (Topic.thesis_provided == True))  # noqa: E712
        ).options(
            selectinload(Topic.scored_signal).selectinload(ScoredSignal.signal),
        )
        result = await session.execute(stmt)
        topics = result.scalars().all()

        if not topics:
            logger.info("No queued topics to generate")
            return {"topics_processed": 0, "drafts_created": 0, "errors": 0}

        client = LLMClient(
            groq_api_key=settings.groq_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )

        counts = {"topics_processed": 0, "drafts_created": 0, "errors": 0}

        for topic in topics:
            try:
                drafts = await generate_for_topic(topic, session, client)
                counts["topics_processed"] += 1
                counts["drafts_created"] += len(drafts)
            except Exception:
                logger.exception("Failed to generate for topic %s", topic.id)
                counts["errors"] += 1

        await session.commit()
        logger.info("Generation complete: %s", counts)

        # Trigger Notion staging
        await run_notion_staging_job(ctx)

        return counts
    finally:
        await session.close()
        await engine.dispose()
```

- [ ] **Step 2: Create Notion staging ARQ job**

```python
# worker/jobs/notion_jobs.py
"""ARQ job for Notion staging.

Stages content drafts in Notion for Justin's review.
Creates Notion pages with properties and metadata comments.

Implements PRD Section 6 (Notion Staging Schema).
"""
from __future__ import annotations

import logging

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory
from worker.notion.staging import stage_drafts
from worker.notion.client import NotionClient

logger = logging.getLogger(__name__)


async def run_notion_staging_job(ctx: dict) -> dict[str, int]:
    """ARQ job: stage unstaged content drafts in Notion.

    Queries ContentDrafts where notion_page_id is null and creates
    Notion pages with rate-limited batching.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Dictionary with counts: {"staged": N, "errors": N}.

    Estimated runtime: ~1s per draft (2 API calls × 400ms delay).
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Per-draft errors logged as system_alerts.
    """
    settings = get_settings()

    if not settings.notion_api_key or not settings.notion_db_id:
        logger.warning("Notion API key or DB ID not configured — skipping staging")
        return {"staged": 0, "errors": 0}

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    session = session_factory()

    try:
        client = NotionClient(
            api_key=settings.notion_api_key,
            database_id=settings.notion_db_id,
        )
        counts = await stage_drafts(session, client)
        await session.commit()
        logger.info("Notion staging complete: %s", counts)
        return counts
    finally:
        await session.close()
        await engine.dispose()
```

- [ ] **Step 3: Update worker.py to register new jobs**

Add imports and register in `WorkerSettings.functions`:
```python
from worker.jobs.generation_jobs import run_generation_job
from worker.jobs.notion_jobs import run_notion_staging_job

# In WorkerSettings.functions list, add:
#   run_generation_job, run_notion_staging_job
```

- [ ] **Step 4: Update pyproject.toml**

Add to `testpaths`: `"generation"`, `"notion"`
Add to `dependencies`: `"notion-client>=2.2.0"`, `"beautifulsoup4>=4.12.0"`, `"anthropic>=0.39.0"`

- [ ] **Step 5: Update conftest.py**

Add dummy env vars:
```python
os.environ.setdefault("NOTION_API_KEY", "")
os.environ.setdefault("NOTION_DB_ID", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
```

- [ ] **Step 6: Run all tests**

```bash
cd worker && python3.12 -m pytest -v
```

Expected: All tests pass (existing + new).

- [ ] **Step 7: Commit**

```bash
git add worker/jobs/generation_jobs.py worker/jobs/notion_jobs.py worker/jobs/worker.py worker/pyproject.toml worker/conftest.py
git commit -m "feat(worker): register generation and Notion staging ARQ jobs"
```

---

### Task 11: Rubric Expansion

**Files:**
- Modify: `worker/scoring/rubric.py`

- [ ] **Step 1: Add sports, media, personal keywords to RESONANCE_TAXONOMY**

Add to `"direct"` keywords:
```python
"seahawks", "seattle seahawks", "nfl", "mike macdonald",
"geno smith", "jaxon smith-njigba", "nfc west",
"media criticism", "false balance", "journalism ethics",
```

Add to `"adjacent"` keywords:
```python
"salary cap", "nfl draft", "football analytics",
"content moderation", "narrative framing",
"neurodivergence", "autism", "indie creator",
```

- [ ] **Step 2: Run existing scoring tests to verify no regressions**

```bash
cd worker && python3.12 -m pytest scoring/ -v
```

Expected: All existing scoring tests still pass.

- [ ] **Step 3: Commit**

```bash
git add worker/scoring/rubric.py
git commit -m "feat(scoring): expand rubric taxonomy with sports, media, personal verticals"
```

---

### Task 12: Exemplar Seeding Script

**Files:**
- Create: `worker/scripts/__init__.py`
- Create: `worker/scripts/seed_exemplars.py`

- [ ] **Step 1: Create seeding script**

Script that:
1. Fetches full article text from 7 Substack URLs using httpx
2. Parses HTML with beautifulsoup4 to extract article body
3. Detects vertical for each article using `worker.generation.verticals.detect_vertical`
4. Inserts into `voice_exemplars` table with `platform=substack`
5. Skips articles already in the table (idempotent)

URLs:
```
https://drinkyouroj.substack.com/p/schneider-solved-the-salary-cap-while-everyone-else-complained
https://drinkyouroj.substack.com/p/13-3-the-box-score-that-ended-the-can-seattles-defense-travel-debate
https://drinkyouroj.substack.com/p/disguise-and-destroy-the-macdonald-method-that-broke-nfl-offenses
https://drinkyouroj.substack.com/p/trump-is-covering-up-the-minneapolis-ice-shooting-just-like-hes-covering-up-epstein
https://drinkyouroj.substack.com/p/nodes-over-numbers
https://drinkyouroj.substack.com/p/the-false-balance-trap
https://drinkyouroj.substack.com/p/my-autism-self-assessment-scores
```

Run: `cd worker && python3.12 -m worker.scripts.seed_exemplars`

- [ ] **Step 2: Commit**

```bash
git add worker/scripts/
git commit -m "feat(generation): add voice exemplar seeding script for Substack articles"
```

---

### Task 13: Model Comparison Script

**Files:**
- Create: `worker/scripts/compare_models.py`

- [ ] **Step 1: Create comparison script**

Script that:
1. Takes a topic ID as argument
2. Generates the same topic through both Groq and Anthropic
3. Saves outputs side-by-side in `output/comparisons/YYYY-MM-DD-<topic-id>/`
4. Prints a summary table (model, word count, token count, estimated cost)

Run: `cd worker && python3.12 -m worker.scripts.compare_models <topic-id>`

- [ ] **Step 2: Commit**

```bash
git add worker/scripts/compare_models.py
git commit -m "feat(generation): add model quality comparison script"
```

---

### Task 14: Decision Doc + Documentation

**Files:**
- Create: `docs/decisions/004-groq-default-generation.md`
- Modify: `worker/generation/README.md` (create)
- Modify: `worker/notion/README.md` (create)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write decision doc**

```markdown
# 004 — Groq as Default Generation Provider
_Date: 2026-03-20 | Status: Accepted_

## Context
The PRD specifies Claude Sonnet for all content generation, noting voice quality
as a bottleneck. However, Groq offers free/cheap inference with llama-3.3-70b
which may be sufficient for initial testing.

## Options Considered
1. Claude Sonnet for all platforms — highest quality, ~$0.08/topic
2. Groq for all platforms — free/cheap, fast, quality unknown
3. Hybrid: Anthropic for Substack, Groq for short-form — best of both

## Decision
Default to Groq for all platforms with per-platform override via env vars.
Use the comparison script to evaluate voice quality empirically.

## Consequences
- Lower cost during development and testing
- Easy upgrade path per platform when quality issues surface
- Risk: voice quality may be insufficient for Substack long-form
```

- [ ] **Step 2: Create README files for new directories**

- [ ] **Step 3: Update CHANGELOG.md**

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/004-groq-default-generation.md worker/generation/README.md worker/notion/README.md CHANGELOG.md
git commit -m "docs(generation): add decision doc, READMEs, and changelog updates"
```

---

### Task 15: Integration Verification

- [ ] **Step 1: Run full test suite**

```bash
cd worker && python3.12 -m pytest -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 2: Seed exemplars (live test)**

```bash
cd worker && python3.12 -m worker.scripts.seed_exemplars
```

Expected: 7 exemplars inserted into Neon.

- [ ] **Step 3: Run generation on a real topic (live test)**

```bash
cd worker && python3.12 -c "
import asyncio
from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory
from worker.generation.llm_client import LLMClient
from worker.generation.engine import generate_for_topic
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from worker.app.models.topic import Topic, TopicStatus

async def main():
    settings = get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    session = factory()
    try:
        result = await session.execute(
            select(Topic).where(Topic.status == TopicStatus.REVIEW)
            .options(selectinload(Topic.scored_signal))
            .limit(1)
        )
        topic = result.scalars().first()
        if not topic:
            print('No review topics found')
            return
        print(f'Generating for: {topic.scored_signal.signal.title}')
        client = LLMClient(groq_api_key=settings.groq_api_key)
        drafts = await generate_for_topic(topic, session, client)
        await session.commit()
        for d in drafts:
            print(f'  {d.platform.value}: {len(d.content)} chars')
    finally:
        await session.close()
        await engine.dispose()

asyncio.run(main())
"
```

Expected: 4 drafts generated, one per platform.

- [ ] **Step 4: Verify Notion staging (live test)**

Only if `NOTION_API_KEY` and `NOTION_DB_ID` are configured:
```bash
cd worker && python3.12 -c "
import asyncio
from worker.jobs.notion_jobs import run_notion_staging_job

asyncio.run(run_notion_staging_job({}))
"
```

Expected: Notion pages created in Second Brain database.

- [ ] **Step 5: Final commit if any live-test fixes needed**

---

## Summary

| Task | Component | Tests | Estimated Complexity |
|------|-----------|-------|---------------------|
| 1 | Alembic migrations + ORM updates | - | S |
| 2 | Vertical detection | 9 | S |
| 3 | LLM client abstraction | 6 | M |
| 4 | Exemplar selector | 4 | S |
| 5 | Platform prompt templates | - | M |
| 6 | Voice-drift critique | 3 | S |
| 7 | Generation engine | 5 | L |
| 8 | Notion client | 5 | M |
| 9 | Notion staging | 4+ | M |
| 10 | ARQ jobs + registration | - | S |
| 11 | Rubric expansion | - | S |
| 12 | Exemplar seeding script | - | S |
| 13 | Model comparison script | - | S |
| 14 | Decision doc + documentation | - | S |
| 15 | Integration verification | - | S |

**Total: 15 tasks, ~36+ unit tests, 2 scripts, 2 migrations**
