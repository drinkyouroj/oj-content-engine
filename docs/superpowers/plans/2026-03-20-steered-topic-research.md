# Steered Topic Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/dashboard/research` page where the user enters a topic query, searches existing signals + Brave Search, selects articles, and creates topics that skip scoring/triage.

**Architecture:** Two new Worker endpoints (`/api/research`, `/api/create-topics`) backed by a `research.py` module. Two new Vercel proxy routes and a research page with result cards. Database migration adds `MANUAL` to SignalSource enum, `signal_id` FK on topics, and makes `scored_signal_id` nullable. All existing queries and generation code updated for nullable scored_signal.

**Tech Stack:** Python (FastAPI, SQLAlchemy, httpx, Brave Search API), TypeScript (Next.js App Router, Neon serverless), Alembic migrations

**Spec:** `docs/superpowers/specs/2026-03-20-steered-topic-research-design.md`

---

### Task 1: Database Migration

**Files:**
- Modify: `worker/app/models/signal.py`
- Modify: `worker/app/models/topic.py`
- Create: `worker/alembic/versions/004_steered_topics.py`

- [ ] **Step 1: Add MANUAL to SignalSource enum**

In `worker/app/models/signal.py`, add to `SignalSource`:

```python
class SignalSource(str, enum.Enum):
    RSS = "rss"
    REDDIT = "reddit"
    HN = "hn"
    TWITTER = "twitter"
    MANUAL = "manual"
```

- [ ] **Step 2: Update Topic model — add signal_id FK, make scored_signal_id nullable**

In `worker/app/models/topic.py`:

```python
import uuid
from sqlalchemy import ForeignKey
from worker.app.models.signal import Signal

class Topic(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "topics"

    scored_signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scored_signals.id", ondelete="CASCADE"), nullable=True
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), nullable=True
    )
    # ... rest unchanged ...

    # Relationships
    scored_signal: Mapped["ScoredSignal | None"] = relationship(back_populates="topics")
    signal: Mapped["Signal | None"] = relationship()
```

- [ ] **Step 3: Write Alembic migration**

Create `worker/alembic/versions/004_steered_topics.py`:

```python
"""Add MANUAL to signal_source enum, add signal_id FK on topics, make scored_signal_id nullable.

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"

def upgrade():
    # Add MANUAL to signal_source enum
    op.execute("ALTER TYPE signal_source ADD VALUE IF NOT EXISTS 'manual'")

    # Add nullable signal_id FK on topics
    op.add_column("topics", sa.Column("signal_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_topics_signal_id", "topics", "signals",
        ["signal_id"], ["id"], ondelete="CASCADE"
    )

    # Make scored_signal_id nullable
    op.alter_column("topics", "scored_signal_id", nullable=True)

    # Backfill signal_id from scored_signals for existing topics
    op.execute("""
        UPDATE topics t
        SET signal_id = ss.signal_id
        FROM scored_signals ss
        WHERE t.scored_signal_id = ss.id
    """)

def downgrade():
    op.drop_constraint("fk_topics_signal_id", "topics", type_="foreignkey")
    op.drop_column("topics", "signal_id")
    op.alter_column("topics", "scored_signal_id", nullable=False)
```

- [ ] **Step 4: Run migration**

```bash
cd worker && python -m alembic upgrade head
```

- [ ] **Step 5: Commit**

```bash
git add worker/app/models/signal.py worker/app/models/topic.py worker/alembic/versions/004_steered_topics.py
git commit -m "feat(db): add MANUAL source, signal_id FK on topics, nullable scored_signal_id"
```

---

### Task 2: Update All Code Paths for Nullable scored_signal

**Files:**
- Modify: `worker/generation/engine.py`
- Modify: `worker/generation/thesis_suggestions.py`
- Modify: `worker/notion/staging.py`
- Modify: `worker/app/main.py` (selectinload chains)
- Modify: `worker/jobs/generation_jobs.py` (selectinload chains)
- Modify: `lib/db.ts`

- [ ] **Step 1: Add get_signal helper to engine.py**

At the top of `worker/generation/engine.py`, after imports, add:

```python
def get_signal(topic: Topic) -> Signal:
    """Get the signal for a topic, whether steered or discovered.

    Steered topics have signal_id set directly. Discovered topics reach
    their signal via scored_signal.signal.

    Args:
        topic: Topic instance with relationships loaded.

    Returns:
        The Signal associated with this topic.

    Raises:
        ValueError: If neither signal path is available.
    """
    if topic.signal is not None:
        return topic.signal
    if topic.scored_signal is not None:
        return topic.scored_signal.signal
    raise ValueError(f"Topic {topic.id} has no signal (neither signal_id nor scored_signal_id set)")
```

- [ ] **Step 2: Update generate_for_topic to use get_signal**

Replace `signal = topic.scored_signal.signal` (line 123) with:

```python
signal = get_signal(topic)
```

Also update score_breakdown access to handle None:

```python
score_breakdown = topic.scored_signal.score_breakdown if topic.scored_signal else {}
```

- [ ] **Step 3: Update generate_social_for_topic to use get_signal**

Same pattern — replace `topic.scored_signal.signal` with `get_signal(topic)` and guard score_breakdown.

- [ ] **Step 4: Update thesis_suggestions.py to use get_signal**

In `worker/generation/thesis_suggestions.py`, replace:
```python
signal = topic.scored_signal.signal
```
with:
```python
from worker.generation.engine import get_signal
signal = get_signal(topic)
scored = topic.scored_signal
breakdown = scored.score_breakdown if scored else {}
```

- [ ] **Step 5: Update notion/staging.py for direct signal access**

In `worker/notion/staging.py`, update signal title access to handle steered topics:
```python
if topic and topic.signal:
    signal_title = topic.signal.title
elif topic and topic.scored_signal and topic.scored_signal.signal:
    signal_title = topic.scored_signal.signal.title
else:
    signal_title = "Unknown"
```

- [ ] **Step 6: Add selectinload(Topic.signal) to all existing query chains**

In `worker/app/main.py` (suggest-theses endpoint ~line 211, generate-social endpoint ~line 289), and `worker/jobs/generation_jobs.py` (~line 74), add `selectinload(Topic.signal)` alongside the existing `selectinload(Topic.scored_signal)`:

```python
.options(
    selectinload(Topic.scored_signal).selectinload(ScoredSignal.signal),
    selectinload(Topic.signal),  # direct signal for steered topics
)
```

- [ ] **Step 7: Update lib/db.ts queries to LEFT JOIN**

Update `getTopicsNeedingAttention`:

```sql
SELECT
  t.id, t.status, t.vertical, t.thesis_provided, t.created_at,
  ss.composite_score, ss.score_breakdown,
  COALESCE(ds.title, s.title) AS title,
  COALESCE(ds.url, s.url) AS url,
  COALESCE(ds.source, s.source) AS source
FROM topics t
LEFT JOIN scored_signals ss ON t.scored_signal_id = ss.id
LEFT JOIN signals s ON ss.signal_id = s.id
LEFT JOIN signals ds ON t.signal_id = ds.id
WHERE t.status IN ('queued', 'review', 'generating', 'generated')
ORDER BY ss.composite_score DESC NULLS LAST
LIMIT 50
```

Update `getRecentDrafts`:

```sql
SELECT
  cd.id, cd.topic_id, cd.platform, cd.status, cd.notion_page_id, cd.created_at,
  COALESCE(ds.title, s.title) AS topic_title
FROM content_drafts cd
JOIN topics t ON cd.topic_id = t.id
LEFT JOIN scored_signals ss ON t.scored_signal_id = ss.id
LEFT JOIN signals s ON ss.signal_id = s.id
LEFT JOIN signals ds ON t.signal_id = ds.id
ORDER BY cd.created_at DESC
LIMIT 20
```

Update `getTopicWithDetails`:

```sql
SELECT
  t.*,
  ss.composite_score, ss.score_breakdown,
  COALESCE(ds.title, s.title) AS signal_title,
  COALESCE(ds.url, s.url) AS signal_url,
  COALESCE(ds.source, s.source) AS source,
  COALESCE(ds.body_preview, s.body_preview) AS body_preview,
  COALESCE(ds.discovered_at, s.discovered_at) AS discovered_at
FROM topics t
LEFT JOIN scored_signals ss ON t.scored_signal_id = ss.id
LEFT JOIN signals s ON ss.signal_id = s.id
LEFT JOIN signals ds ON t.signal_id = ds.id
WHERE t.id = ${topicId}::uuid
```

- [ ] **Step 8: Commit**

```bash
git add worker/generation/engine.py worker/generation/thesis_suggestions.py worker/notion/staging.py worker/app/main.py worker/jobs/generation_jobs.py lib/db.ts
git commit -m "refactor(generation): handle nullable scored_signal across queries and engine"
```

---

### Task 3: Worker Research Module

**Files:**
- Create: `worker/discovery/research.py`
- Create: `worker/discovery/test_research.py`
- Modify: `worker/app/config.py`

- [ ] **Step 1: Add brave_search_api_key to config**

In `worker/app/config.py`, add:

```python
brave_search_api_key: str = ""
```

- [ ] **Step 2: Write test for search_existing_signals**

Create `worker/discovery/test_research.py`:

```python
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock
from worker.discovery.research import search_existing_signals, search_web, merge_and_deduplicate

@pytest.mark.asyncio
async def test_search_existing_signals_returns_matching_results():
    """ILIKE search should match signals by title or body_preview."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"title": "Seahawks draft strategy", "url": "https://example.com/seahawks", "body_preview": "NFL offseason analysis", "source": "rss", "discovered_at": "2026-03-20T00:00:00Z"}
    ]
    mock_session.execute.return_value = mock_result

    results = await search_existing_signals("Seahawks", mock_session, limit=10)
    assert len(results) == 1
    assert results[0]["title"] == "Seahawks draft strategy"

@pytest.mark.asyncio
async def test_search_web_returns_results(respx_mock):
    """Brave Search API should return formatted results."""
    respx_mock.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(200, json={
            "web": {"results": [
                {"title": "NFL Draft Analysis", "url": "https://example.com/nfl", "description": "Draft picks breakdown"},
            ]}
        })
    )
    results = await search_web("NFL draft", "fake-key", limit=5)
    assert len(results) == 1
    assert results[0]["source"] == "web"

@pytest.mark.asyncio
async def test_search_web_returns_empty_on_failure(respx_mock):
    """Brave Search should return empty list on API failure, not raise."""
    respx_mock.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(500)
    )
    results = await search_web("test", "fake-key")
    assert results == []

def test_merge_and_deduplicate_removes_duplicate_urls():
    """Merge should deduplicate by URL, preferring DB results."""
    db_results = [
        {"title": "A", "url": "https://example.com/a", "body_preview": "...", "source": "rss", "published_at": None}
    ]
    web_results = [
        {"title": "A (web)", "url": "https://example.com/a", "body_preview": "...", "source": "web", "published_at": None},
        {"title": "B", "url": "https://example.com/b", "body_preview": "...", "source": "web", "published_at": None},
    ]
    merged = merge_and_deduplicate(db_results, web_results, max_results=15)
    assert len(merged) == 2
    assert merged[0]["title"] == "A"  # DB version preferred
    assert merged[1]["title"] == "B"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd worker && python -m pytest discovery/test_research.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 4: Implement research.py**

Create `worker/discovery/research.py`:

```python
"""
Research module for steered topic discovery.

Searches existing signals in Postgres and supplements with Brave Search API
results. Used by the /api/research endpoint for on-demand topic research.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, or_, cast, Text
from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.signal import Signal

logger = logging.getLogger(__name__)


async def search_existing_signals(
    query: str,
    session: AsyncSession,
    limit: int = 10,
) -> list[dict]:
    """Search existing signals by title and body_preview using ILIKE.

    Args:
        query: Search query string.
        session: Async SQLAlchemy session.
        limit: Max results to return.

    Returns:
        List of dicts with title, url, body_preview, source, published_at.
    """
    escaped = query.replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    stmt = (
        select(
            Signal.title,
            Signal.url,
            Signal.body_preview,
            Signal.source,
            Signal.discovered_at,
        )
        .where(
            or_(
                Signal.title.ilike(pattern),
                Signal.body_preview.ilike(pattern),
            )
        )
        .order_by(Signal.discovered_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.mappings().all()

    return [
        {
            "title": row["title"],
            "url": row["url"],
            "body_preview": (row["body_preview"] or "")[:200],
            "source": row["source"].value if hasattr(row["source"], "value") else str(row["source"]),
            "published_at": row["discovered_at"].isoformat() if row["discovered_at"] else None,
        }
        for row in rows
    ]


async def search_web(
    query: str,
    api_key: str,
    limit: int = 10,
) -> list[dict]:
    """Search the web via Brave Search API.

    Args:
        query: Search query string.
        api_key: Brave Search API key.
        limit: Max results to return.

    Returns:
        List of dicts with title, url, body_preview, source, published_at.
        Returns empty list if the API call fails.
    """
    if not api_key:
        logger.warning("Brave Search API key not configured, skipping web search")
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": limit, "freshness": "pw"},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("web", {}).get("results", [])[:limit]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "body_preview": (item.get("description", ""))[:200],
                "source": "web",
                "published_at": item.get("page_age") or item.get("age"),
            })
        return results

    except Exception:
        logger.exception("Brave Search API call failed for query: %s", query)
        return []


def merge_and_deduplicate(
    db_results: list[dict],
    web_results: list[dict],
    max_results: int = 15,
) -> list[dict]:
    """Merge DB and web results, deduplicate by URL, prefer DB results.

    Args:
        db_results: Results from search_existing_signals.
        web_results: Results from search_web.
        max_results: Maximum total results to return.

    Returns:
        Deduplicated merged list, DB results first.
    """
    seen_urls: set[str] = set()
    merged: list[dict] = []

    for result in db_results + web_results:
        url = result.get("url", "").rstrip("/").lower()
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(result)
        if len(merged) >= max_results:
            break

    return merged
```

- [ ] **Step 5: Run tests**

```bash
cd worker && python -m pytest discovery/test_research.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add worker/app/config.py worker/discovery/research.py worker/discovery/test_research.py
git commit -m "feat(discovery): add research module for steered topic search"
```

---

### Task 4: Worker API Endpoints

**Files:**
- Modify: `worker/app/main.py`

- [ ] **Step 1: Add POST /api/research endpoint**

Add to `worker/app/main.py` before the `/health` route:

```python
from pydantic import BaseModel

class ResearchRequest(BaseModel):
    query: str

@app.post("/api/research")
async def research_endpoint(
    body: ResearchRequest,
    x_worker_secret: str = Header(None),
):
    """Search existing signals + Brave Search for topic research."""
    if not x_worker_secret or not _settings or x_worker_secret != _settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")
    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Worker not ready")

    from worker.discovery.research import search_existing_signals, search_web, merge_and_deduplicate

    warnings = []

    async with _session_factory() as session:
        db_results = await search_existing_signals(body.query, session)

    web_results = await search_web(body.query, _settings.brave_search_api_key)
    if not web_results and _settings.brave_search_api_key:
        warnings.append("Brave Search unavailable")

    merged = merge_and_deduplicate(db_results, web_results)
    return {"results": merged, "warnings": warnings}
```

- [ ] **Step 2: Add POST /api/create-topics endpoint**

```python
class ArticleInput(BaseModel):
    title: str
    url: str
    body_preview: str | None = None
    source: str = "web"

class CreateTopicsRequest(BaseModel):
    articles: list[ArticleInput]

@app.post("/api/create-topics")
async def create_topics_endpoint(
    body: CreateTopicsRequest,
    x_worker_secret: str = Header(None),
):
    """Create topics directly from selected research articles, skipping scoring."""
    if not x_worker_secret or not _settings or x_worker_secret != _settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")
    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Worker not ready")

    from sqlalchemy import select
    from worker.app.models.signal import Signal, SignalSource
    from worker.app.models.scored_signal import ScoredSignal
    from worker.app.models.topic import Topic, TopicStatus
    from worker.discovery.dedup import compute_dedup_hash, normalize_url

    created = 0
    skipped = 0
    topic_ids = []

    async with _session_factory() as session:
        for article in body.articles:
            normalized = normalize_url(article.url)
            dedup_hash = compute_dedup_hash(normalized)

            # Check for existing signal — reuse it if found
            existing = await session.execute(
                select(Signal.id).where(Signal.dedup_hash == dedup_hash)
            )
            existing_signal_id = existing.scalar_one_or_none()

            if existing_signal_id is not None:
                # Signal exists — check if a topic already exists for it
                existing_topic = await session.execute(
                    select(Topic.id).where(
                        (Topic.signal_id == existing_signal_id)
                        | (Topic.scored_signal_id.in_(
                            select(ScoredSignal.id).where(ScoredSignal.signal_id == existing_signal_id)
                        ))
                    )
                )
                if existing_topic.scalar_one_or_none() is not None:
                    skipped += 1
                    continue

                # Reuse existing signal, create new topic
                signal_id = existing_signal_id
            else:
                # Create new signal
                signal = Signal(
                    source=SignalSource.MANUAL,
                    url=article.url,
                    title=article.title,
                    body_preview=(article.body_preview or "")[:500] or None,
                    discovered_at=datetime.now(timezone.utc),
                    source_metrics=None,
                    dedup_hash=dedup_hash,
                )
                session.add(signal)
                await session.flush()
                signal_id = signal.id

            # Create topic (skip scoring)
            topic = Topic(
                signal_id=signal_id,
                scored_signal_id=None,
                status=TopicStatus.QUEUED,
                queued_at=datetime.now(timezone.utc),
            )
            session.add(topic)
            await session.flush()

            topic_ids.append(str(topic.id))
            created += 1

        await session.commit()

    return {"created": created, "skipped": skipped, "topic_ids": topic_ids}
```

- [ ] **Step 3: Add datetime import if not already present**

Ensure `from datetime import datetime, timezone` is imported at the top of `main.py`.

- [ ] **Step 4: Commit**

```bash
git add worker/app/main.py
git commit -m "feat(worker): add /api/research and /api/create-topics endpoints"
```

---

### Task 5: Vercel Proxy Routes and Worker Client

**Files:**
- Create: `app/api/research/route.ts`
- Create: `app/api/create-topics/route.ts`
- Modify: `lib/worker-client.ts`

- [ ] **Step 1: Add worker client functions**

Add to `lib/worker-client.ts`:

```typescript
export async function searchResearch(
  query: string
): Promise<{ results: Array<{ title: string; url: string; body_preview: string; source: string; published_at: string | null }>; warnings: string[] }> {
  const workerUrl = process.env.WORKER_URL;
  const workerSecret = process.env.WORKER_SECRET;
  if (!workerUrl || !workerSecret) throw new WorkerClientError("WORKER_URL or WORKER_SECRET not configured");

  const response = await fetch(`${workerUrl}/api/research`, {
    method: "POST",
    headers: { "x-worker-secret": workerSecret, "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new WorkerClientError(`Worker API error: ${text}`, response.status);
  }
  return response.json();
}

export async function createTopicsFromArticles(
  articles: Array<{ title: string; url: string; body_preview?: string; source?: string }>
): Promise<{ created: number; skipped: number; topic_ids: string[] }> {
  const workerUrl = process.env.WORKER_URL;
  const workerSecret = process.env.WORKER_SECRET;
  if (!workerUrl || !workerSecret) throw new WorkerClientError("WORKER_URL or WORKER_SECRET not configured");

  const response = await fetch(`${workerUrl}/api/create-topics`, {
    method: "POST",
    headers: { "x-worker-secret": workerSecret, "Content-Type": "application/json" },
    body: JSON.stringify({ articles }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new WorkerClientError(`Worker API error: ${text}`, response.status);
  }
  return response.json();
}
```

- [ ] **Step 2: Create app/api/research/route.ts**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { searchResearch, WorkerClientError } from "@/lib/worker-client";

export async function POST(request: NextRequest) {
  const { query } = await request.json();
  if (!query || typeof query !== "string") {
    return NextResponse.json({ error: "query required" }, { status: 400 });
  }

  try {
    const result = await searchResearch(query.trim());
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof WorkerClientError) {
      return NextResponse.json({ error: error.message }, { status: error.status || 502 });
    }
    throw error;
  }
}
```

- [ ] **Step 3: Create app/api/create-topics/route.ts**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { createTopicsFromArticles, WorkerClientError } from "@/lib/worker-client";

export async function POST(request: NextRequest) {
  const { articles } = await request.json();
  if (!articles || !Array.isArray(articles) || articles.length === 0) {
    return NextResponse.json({ error: "articles array required" }, { status: 400 });
  }

  try {
    const result = await createTopicsFromArticles(articles);
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof WorkerClientError) {
      return NextResponse.json({ error: error.message }, { status: error.status || 502 });
    }
    throw error;
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add lib/worker-client.ts app/api/research/route.ts app/api/create-topics/route.ts
git commit -m "feat(vercel): add research and create-topics proxy routes"
```

---

### Task 6: Research Page UI

**Files:**
- Create: `app/dashboard/research/page.tsx`
- Create: `components/research-results.tsx`

- [ ] **Step 1: Create the research results client component**

Create `components/research-results.tsx` — a client component with:
- State for selected articles (Set of URLs)
- Result cards with checkbox, title, source badge, URL link, body preview, date
- "Create N Topics" button at bottom
- Loading/success/error states
- Calls `POST /api/create-topics` on submit
- On success, shows "Created N topics" with link to dashboard

Source badge colors: `rss` → zinc, `reddit` → orange, `hn` → amber, `twitter` → blue, `web` → teal

- [ ] **Step 2: Create the research page**

Create `app/dashboard/research/page.tsx` — a server component with:
- Page title "Research Topics"
- Client-side search form (wrapped in a client component or using the results component)
- Calls `POST /api/research` on submit, passes results to ResearchResults
- Back link to dashboard

- [ ] **Step 3: Add navigation link from dashboard**

Add a "Research" link/button on the dashboard page (`app/dashboard/page.tsx`) that navigates to `/dashboard/research`.

- [ ] **Step 4: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add app/dashboard/research/page.tsx components/research-results.tsx app/dashboard/page.tsx
git commit -m "feat(approval-ui): add /dashboard/research page for steered topic discovery"
```

---

### Task 7: Update .env.example, Test End-to-End, Push

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add BRAVE_SEARCH_API_KEY to .env.example**

Add to the Discovery Sources section:

```bash
BRAVE_SEARCH_API_KEY=...              # Brave Search API key (free tier: 2,000 queries/month)
```

- [ ] **Step 2: Test the full flow locally**

1. Start Worker: `cd worker && uvicorn worker.app.main:app --port 8001`
2. Start Next.js: `npm run dev`
3. Navigate to `/dashboard/research`
4. Search for a topic
5. Select results and create topics
6. Verify topics appear on dashboard

- [ ] **Step 3: Commit and push**

```bash
git add .env.example
git commit -m "docs: add BRAVE_SEARCH_API_KEY to .env.example"
git push origin feature/steered-topic-research
```

- [ ] **Step 4: Set BRAVE_SEARCH_API_KEY on Railway**

```bash
railway variable set BRAVE_SEARCH_API_KEY=<key> --service worker
```

- [ ] **Step 5: Deploy Vercel**

```bash
vercel --prod
```
