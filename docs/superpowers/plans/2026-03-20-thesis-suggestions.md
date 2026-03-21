# Thesis Suggestions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Suggest Theses" button to the topic review page that generates 3-5 thesis options via Claude Haiku 4.5 using the full source article and score breakdown.

**Architecture:** Worker-side LLM call (fetches source article, assembles prompt, calls Haiku). Next.js proxies the request. UI renders clickable thesis cards that populate the textarea.

**Tech Stack:** Python (httpx, beautifulsoup4, anthropic via LLMClient), TypeScript/Next.js, shadcn/ui

**Spec:** `docs/superpowers/specs/2026-03-20-thesis-suggestions-design.md`

**Branch:** `feature/thesis-suggestions`

---

### Task 1: Thesis Suggestion Module (Worker)

**Files:**
- Create: `worker/generation/thesis_suggestions.py`
- Create: `worker/generation/test_thesis_suggestions.py`
- Modify: `worker/generation/llm_client.py` — add `thesis_suggest` to GENERATION_MODELS

- [ ] **Step 1: Add thesis_suggest to GENERATION_MODELS**

In `worker/generation/llm_client.py`, add to the `GENERATION_MODELS` dict:
```python
"thesis_suggest": {"provider": "anthropic", "model": "claude-haiku-4-5"},
```

- [ ] **Step 2: Write failing tests**

```python
# worker/generation/test_thesis_suggestions.py
"""Tests for thesis suggestion generation."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.generation.thesis_suggestions import suggest_theses, _parse_theses, _fetch_article
from worker.generation.llm_client import LLMResponse


def _make_topic():
    topic = MagicMock()
    topic.id = uuid.uuid4()
    topic.thesis = None

    signal = MagicMock()
    signal.title = "AI Safety Theater Problem"
    signal.url = "https://example.com/article"
    signal.body_preview = "A deep dive into AI safety frameworks that don't work"
    signal.source_metrics = {"upvotes": 200}

    scored_signal = MagicMock()
    scored_signal.composite_score = 72.0
    scored_signal.score_breakdown = {
        "signal_strength": 80, "timing_window": 70, "depth_potential": 75,
        "novelty": 65, "community_resonance": 60, "brand_angle_availability": 85,
    }
    scored_signal.signal = signal

    topic.scored_signal = scored_signal
    return topic


class TestParseTheses:
    def test_parses_numbered_list(self):
        raw = "1. First thesis here.\n2. Second thesis here.\n3. Third thesis."
        result = _parse_theses(raw)
        assert len(result) == 3
        assert result[0] == "First thesis here."
        assert result[2] == "Third thesis."

    def test_parses_with_extra_whitespace(self):
        raw = "1.  First thesis.\n\n2.  Second thesis.\n\n3.  Third thesis."
        result = _parse_theses(raw)
        assert len(result) == 3

    def test_fallback_on_unparseable(self):
        raw = "Here is a single thesis about the topic."
        result = _parse_theses(raw)
        assert len(result) == 1
        assert result[0] == raw.strip()

    def test_strips_numbering(self):
        raw = "1) First. 2) Second. 3) Third."
        result = _parse_theses(raw)
        assert not result[0].startswith("1")


class TestFetchArticle:
    @pytest.mark.asyncio
    async def test_returns_text_on_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><article><p>Article content here.</p></article></body></html>"

        with patch("worker.generation.thesis_suggestions.httpx.AsyncClient") as MockClient:
            instance = MockClient.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            instance = MockClient.return_value
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get = AsyncMock(return_value=mock_response)

            text = await _fetch_article("https://example.com/article")
            assert "Article content" in text

    @pytest.mark.asyncio
    async def test_returns_empty_on_failure(self):
        with patch("worker.generation.thesis_suggestions.httpx.AsyncClient") as MockClient:
            instance = MockClient.return_value
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get = AsyncMock(side_effect=Exception("timeout"))

            text = await _fetch_article("https://example.com/bad")
            assert text == ""


class TestSuggestTheses:
    @pytest.mark.asyncio
    async def test_returns_thesis_list(self):
        topic = _make_topic()
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="1. AI safety frameworks are theater.\n2. Regulation without enforcement.\n3. The compliance industrial complex.",
            total_tokens=300,
            model="claude-haiku-4-5",
            provider="anthropic",
        ))

        with patch("worker.generation.thesis_suggestions._fetch_article", return_value="Full article text here"):
            result = await suggest_theses(topic, mock_client)

        assert len(result) == 3
        assert "theater" in result[0].lower()
        mock_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_body_preview(self):
        topic = _make_topic()
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="1. Thesis one.\n2. Thesis two.\n3. Thesis three.",
            total_tokens=200,
            model="claude-haiku-4-5",
            provider="anthropic",
        ))

        with patch("worker.generation.thesis_suggestions._fetch_article", return_value=""):
            result = await suggest_theses(topic, mock_client)

        assert len(result) == 3
        # Verify body_preview was used in the prompt
        call_kwargs = mock_client.generate.call_args.kwargs
        assert "AI safety frameworks" in call_kwargs["user_prompt"]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd worker && python3.12 -m pytest generation/test_thesis_suggestions.py -v
```

- [ ] **Step 4: Implement thesis suggestions module**

```python
# worker/generation/thesis_suggestions.py
"""Thesis suggestion generation — uses Claude Haiku to propose 3-5 angles.

Fetches the full source article, combines with score breakdown and brand
context, and asks Haiku to generate thesis statement options for Justin
to choose from.

Inputs:
    - Topic with scored_signal.signal (URL, title, body_preview)
    - LLMClient configured with Anthropic API key

Outputs:
    - List of 3-5 thesis statement strings
"""
from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from worker.generation.llm_client import LLMClient, LLMGenerationError, get_model_config

logger = logging.getLogger(__name__)

_MAX_ARTICLE_CHARS = 4000

_SYSTEM_PROMPT = """\
You are a thesis generator for the drinkYourOJ content brand.

Brand context:
- Voice: Intellectual stand-up comedy. Dry, direct, systems-thinker, anti-hype.
- Core topics: AI infrastructure/critique, tech policy/regulation, DePIN, \
Seahawks/NFL analytics, media criticism, solopreneur culture.
- Audience: Technically literate, skeptical of hype, trust nuance over enthusiasm.
- Hard filters: No "AI is changing everything" breathless takes, no token price \
speculation, no press-release tone, no bandwagon takes.

Your job: generate 3-5 thesis statements for a potential drinkYourOJ article. \
Each thesis should be:
- 2-3 sentences long
- Contrarian or non-obvious — not the take everyone else is writing
- Specific enough to anchor an entire article
- Distinct from the other options — each suggests a different angle

Respond with a numbered list (1. through 5.) and nothing else. No preamble, \
no commentary, no "Here are some options:" — just the numbered theses.\
"""


async def _fetch_article(url: str) -> str:
    """Fetch and extract article body text from a URL.

    Args:
        url: Source article URL.

    Returns:
        Plain text article content, truncated to _MAX_ARTICLE_CHARS.
        Empty string if fetch or parse fails.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to fetch article %s: %s", url, exc)
        return ""

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove noise
        for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # Try common article selectors
        article = (
            soup.find("article")
            or soup.find(class_=re.compile(r"post-content|article-body|entry-content|body-markup"))
            or soup.find("main")
            or soup.body
        )

        text = article.get_text(separator="\n", strip=True) if article else ""
        return text[:_MAX_ARTICLE_CHARS]
    except Exception as exc:
        logger.warning("Failed to parse article %s: %s", url, exc)
        return ""


def _parse_theses(raw: str) -> list[str]:
    """Parse a numbered list of theses from LLM output.

    Handles formats like "1. Thesis" or "1) Thesis".
    Falls back to returning the entire response as a single thesis.

    Args:
        raw: Raw LLM response text.

    Returns:
        List of thesis strings with numbering stripped.
    """
    # Try splitting on numbered patterns: "1.", "2.", "1)", "2)" etc.
    parts = re.split(r"\n\s*\d+[.)]\s*", raw.strip())
    # First element is usually empty or preamble before "1."
    theses = [p.strip() for p in parts if p.strip()]

    if not theses:
        # Fallback: return whole response as one thesis
        return [raw.strip()] if raw.strip() else []

    return theses


async def suggest_theses(
    topic: object,
    llm_client: LLMClient,
) -> list[str]:
    """Generate 3-5 thesis suggestions for a topic.

    Fetches the source article, combines with score breakdown, and calls
    Claude Haiku to generate thesis options.

    Args:
        topic: Topic ORM instance with scored_signal.signal loaded.
        llm_client: Configured LLMClient with Anthropic key.

    Returns:
        List of 3-5 thesis statement strings.

    Raises:
        LLMGenerationError: If the LLM call fails after retries.
    """
    signal = topic.scored_signal.signal
    scored = topic.scored_signal

    # Fetch full article
    article_text = await _fetch_article(signal.url)
    if not article_text:
        logger.info("Using body_preview fallback for %s", signal.url)
        article_text = signal.body_preview or signal.title

    # Format score breakdown
    breakdown = scored.score_breakdown or {}
    score_lines = "\n".join(
        f"  {dim.replace('_', ' ').title()}: {score}/100"
        for dim, score in breakdown.items()
    )

    user_prompt = (
        f"Topic: {signal.title}\n"
        f"Composite Score: {scored.composite_score}\n\n"
        f"Score Breakdown:\n{score_lines}\n\n"
        f"Source Article:\n{article_text}\n\n"
        f"Generate 3-5 thesis statements for a drinkYourOJ article about this topic."
    )

    config = get_model_config("thesis_suggest")
    response = await llm_client.generate(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        provider=config["provider"],
        model=config["model"],
        max_tokens=1024,
        temperature=0.8,
    )

    theses = _parse_theses(response.content)
    logger.info("Generated %d thesis suggestions for topic %s", len(theses), topic.id)
    return theses
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd worker && python3.12 -m pytest generation/test_thesis_suggestions.py -v
```

- [ ] **Step 6: Run full Worker test suite**

```bash
cd worker && python3.12 -m pytest -x --tb=short -q
```

- [ ] **Step 7: Commit**

```bash
git add worker/generation/thesis_suggestions.py worker/generation/test_thesis_suggestions.py worker/generation/llm_client.py
git commit -m "feat(generation): add thesis suggestion module with article fetching"
```

---

### Task 2: Worker API Endpoint

**Files:**
- Modify: `worker/app/main.py` — add `POST /api/suggest-theses/{topic_id}`

- [ ] **Step 1: Add endpoint to FastAPI app**

Add after the existing `/api/regenerate/{topic_id}` endpoint in `worker/app/main.py`:

```python
@app.post("/api/suggest-theses/{topic_id}")
async def suggest_theses_endpoint(
    topic_id: UUID,
    x_worker_secret: str = Header(None),
):
    """Generate 3-5 thesis suggestions for a topic.

    Fetches source article, combines with score data, calls Claude Haiku.
    Requires x-worker-secret header for authentication.

    Estimated runtime: 5-15s (article fetch + LLM call).
    Failure mode: returns error JSON, does not affect topic state.
    """
    if not x_worker_secret or not _settings or x_worker_secret != _settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")

    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Worker not ready")

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from worker.app.models.topic import Topic
    from worker.app.models.scored_signal import ScoredSignal
    from worker.generation.thesis_suggestions import suggest_theses
    from worker.generation.llm_client import LLMClient

    async with _session_factory() as session:
        result = await session.execute(
            select(Topic)
            .where(Topic.id == topic_id)
            .options(
                selectinload(Topic.scored_signal).selectinload(ScoredSignal.signal)
            )
        )
        topic = result.scalars().first()

    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    client = LLMClient(
        anthropic_api_key=_settings.anthropic_api_key,
        groq_api_key=_settings.groq_api_key,
    )

    try:
        theses = await suggest_theses(topic, client)
        return {"theses": theses}
    except Exception as exc:
        logger.exception("Failed to generate thesis suggestions for %s", topic_id)
        raise HTTPException(status_code=500, detail=str(exc))
```

- [ ] **Step 2: Run Worker tests**

```bash
cd worker && python3.12 -m pytest -x --tb=short -q
```

- [ ] **Step 3: Commit**

```bash
git add worker/app/main.py
git commit -m "feat(worker): add thesis suggestions API endpoint"
```

---

### Task 3: Next.js Proxy Route + Worker Client

**Files:**
- Create: `app/api/suggest-theses/route.ts`
- Modify: `lib/worker-client.ts` — add `suggestTheses()` function

- [ ] **Step 1: Add suggestTheses to worker client**

Add to `lib/worker-client.ts`:

```typescript
/**
 * Requests thesis suggestions from the Worker for a given topic.
 *
 * @param topicId UUID of the topic
 * @returns Object containing array of thesis strings
 * @throws WorkerClientError on failure
 */
export async function suggestTheses(
  topicId: string
): Promise<{ theses: string[] }> {
  const workerUrl = process.env.WORKER_URL;
  const workerSecret = process.env.WORKER_SECRET;

  if (!workerUrl || !workerSecret) {
    throw new WorkerClientError("WORKER_URL or WORKER_SECRET not configured");
  }

  const response = await fetch(`${workerUrl}/api/suggest-theses/${topicId}`, {
    method: "POST",
    headers: {
      "x-worker-secret": workerSecret,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new WorkerClientError(`Worker API error: ${text}`, response.status);
  }

  return response.json() as Promise<{ theses: string[] }>;
}
```

- [ ] **Step 2: Create proxy route**

`app/api/suggest-theses/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { suggestTheses, WorkerClientError } from "@/lib/worker-client";

export async function POST(request: NextRequest) {
  const { topicId } = await request.json();
  if (!topicId) {
    return NextResponse.json({ error: "topicId required" }, { status: 400 });
  }

  try {
    const result = await suggestTheses(topicId);
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof WorkerClientError) {
      return NextResponse.json(
        { theses: [], error: error.message },
        { status: error.status || 502 }
      );
    }
    throw error;
  }
}
```

- [ ] **Step 3: Build check**

```bash
npm run build
```

- [ ] **Step 4: Commit**

```bash
git add lib/worker-client.ts app/api/suggest-theses/route.ts
git commit -m "feat(approval-ui): add thesis suggestions proxy route"
```

---

### Task 4: UI — Thesis Suggestion Cards

**Files:**
- Modify: `components/thesis-input.tsx`

- [ ] **Step 1: Update thesis input component**

Add to the existing `thesis-input.tsx` component:

1. New state: `suggestions: string[]`, `loadingSuggestions: boolean`
2. "Suggest Theses" button (outline style, teal accent) — shown when thesis is not provided and no suggestions loaded yet
3. Loading state: "Generating suggestions..." with spinner
4. Thesis cards: map over suggestions, render each as a `bg-zinc-800 hover:bg-zinc-700 hover:border-[#00B4D8]` card with the thesis text. `cursor-pointer`. On click: set the textarea value to that thesis text.
5. After cards are shown, the "Suggest Theses" button changes to "Get New Suggestions" to regenerate

The flow:
- User sees textarea + "Save Thesis" button + "Suggest Theses" button
- Clicks "Suggest Theses" → loading spinner → 3-5 cards appear above textarea
- Clicks a card → textarea populates with that thesis
- User edits the thesis in textarea → clicks "Save Thesis" (existing flow)

Key implementation details:
- Fetch call: `POST /api/suggest-theses` with `{ topicId }`
- Response: `{ theses: ["...", "...", ...] }`
- Error handling: show error message if fetch fails, don't block the manual input
- Cards should also be visible in edit mode (when existing thesis is being edited)

- [ ] **Step 2: Build check**

```bash
npm run build
```

- [ ] **Step 3: Commit**

```bash
git add components/thesis-input.tsx
git commit -m "feat(approval-ui): add thesis suggestion cards to review page"
```

---

### Task 5: Integration Verification

- [ ] **Step 1: Run Worker tests**

```bash
cd worker && python3.12 -m pytest -x --tb=short -q
```

- [ ] **Step 2: Run Next.js build**

```bash
npm run build
```

- [ ] **Step 3: Live test**

Start all three services:
```bash
# Terminal 1: ARQ worker
cd worker && python3.12 -m arq worker.jobs.worker.WorkerSettings

# Terminal 2: FastAPI
cd worker && python3.12 -m uvicorn worker.app.main:app --port 8001

# Terminal 3: Next.js
npm run dev
```

Go to a topic review page, click "Suggest Theses", verify 3-5 cards appear, click one, verify textarea populates, save.

- [ ] **Step 4: Commit any fixes**

---

## Summary

| Task | Component | Complexity |
|------|-----------|------------|
| 1 | Thesis suggestion module + tests | M |
| 2 | Worker API endpoint | S |
| 3 | Next.js proxy route + worker client | S |
| 4 | UI thesis cards | M |
| 5 | Integration verification | S |

**Total: 5 tasks, ~8 tests, 3 new files, 3 modified files**
