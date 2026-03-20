# Steered Topic Research

_Date: 2026-03-20 | Status: Approved_

## Problem

The content pipeline discovers topics passively via RSS, Reddit, and HN pollers. There is no way to direct the engine toward a specific subject. If Justin wants to write about the Seahawks and the NFL offseason, he must wait for a poller to surface a relevant signal — or manually create database rows.

## Solution

Add a research page at `/dashboard/research` where Justin enters a topic query. The system searches existing signals in Postgres and supplements with Brave Search API results. Justin selects articles from the results, and those become topics on the dashboard — skipping scoring and triage since they were hand-picked. From there the normal flow applies: write thesis, generate Substack, optionally generate social content.

## Flow

```
/dashboard/research → enter query → Worker searches DB + web
→ returns 10-15 articles → select 1+ → "Create Topics"
→ topics appear on dashboard → thesis → Substack → socials
```

## Architecture

### New Worker Endpoints

**`POST /api/research`**

- Input: `{ "query": "Seahawks NFL offseason" }`
- Behavior:
  1. Search `signals` table with `ILIKE` on `title` and `body_preview` (limit 10)
  2. Call Brave Search API for recent web articles (limit 10, timeout 10s)
  3. Deduplicate by URL, prefer DB results
  4. Return merged list (max 15 results)
- Output: `{ "results": [{ "title", "url", "body_preview", "source", "published_at" }], "warnings": [] }`
- If Brave Search fails or times out, return DB results only with `warnings: ["Brave Search unavailable"]`
- Auth: `x-worker-secret` header
- Error shape: `{ "detail": "..." }` (standard FastAPI HTTPException)

**`POST /api/create-topics`**

- Input: `{ "articles": [{ "title", "url", "body_preview", "source" }] }`
- Behavior:
  1. Single transaction for the batch
  2. For each article, compute `dedup_hash` as SHA-256 of normalized URL (same logic as existing pollers)
  3. Check `dedup_hash` existence — if found, increment `skipped` and continue
  4. Create a `Signal` row with `source = MANUAL`, `discovered_at` = article's `published_at` or `utcnow()`, `source_metrics = null`
  5. Create a `Topic` row with `status = queued`, `signal_id = <new signal>`, `scored_signal_id = NULL`
  6. Commit once at end
- Output: `{ "created": N, "skipped": N, "topic_ids": [...] }`
- Auth: `x-worker-secret` header

### New Vercel Routes

- `POST /api/research` — proxy to Worker `/api/research`
- `POST /api/create-topics` — proxy to Worker `/api/create-topics`

### New Vercel Page

**`/dashboard/research/page.tsx`**

- Search bar with submit button (client-side debounce, 500ms)
- Loading state while searching
- Result cards showing: title, source badge (Reddit/HN/RSS/Web), URL, body preview (200 chars), published date
- Checkbox selection on each card
- "Create N Topics" button (disabled when none selected)
- Success state: "Created N topics" with link back to dashboard
- Navigation: link from dashboard sidebar or header

### Worker Module

**`worker/discovery/research.py`**

- `search_existing_signals(query, session, limit=10)` — parameterized `ILIKE` search on signals table (no string interpolation)
- `search_web(query, api_key, limit=10)` — Brave Search API call via httpx, 10s timeout
- `merge_and_deduplicate(db_results, web_results, max_results=15)` — deduplicate by URL, prefer DB results

Note: `ILIKE '%query%'` cannot use B-tree indexes and will full-scan. Acceptable for v1 given signal table size (~thousands of rows). If performance becomes an issue, add a GIN trigram index (`pg_trgm`) on `signals.title` and `signals.body_preview`.

## Data Model Changes

### `SignalSource` Enum

Add `MANUAL = "manual"` to the existing enum in `worker/app/models/signal.py`.

Requires Alembic migration to add the enum value to Postgres.

### `topics.signal_id` (new column)

Add a direct FK `signal_id` to `topics` referencing `signals.id`. Nullable for backward compatibility — existing topics reach their signal via `scored_signal → signal`. Steered topics use `signal_id` directly since they have no `scored_signal`.

This avoids the problem of making `scored_signal_id` nullable breaking every INNER JOIN and `topic.scored_signal.signal` access across the codebase (6+ locations in `lib/db.ts`, `engine.py`, `main.py`, `thesis_suggestions.py`).

### `topics.scored_signal_id`

Make nullable. Steered topics have `scored_signal_id = NULL`.

### Relationship updates in `worker/app/models/topic.py`

- Add `signal: Mapped[Signal | None] = relationship(...)` for direct signal access
- Change `scored_signal: Mapped[ScoredSignal]` to `Mapped[ScoredSignal | None]`

### Migration

Single Alembic migration:
1. Add `MANUAL` to `signalsource` enum
2. Add nullable `signal_id` FK on `topics`
3. Make `scored_signal_id` nullable on `topics`
4. Backfill `signal_id` for existing topics: `UPDATE topics SET signal_id = ss.signal_id FROM scored_signals ss WHERE topics.scored_signal_id = ss.id`

### Accessing signal data

Code that needs signal title/URL/body should use a helper:

```python
def get_signal(topic: Topic) -> Signal:
    """Get the signal for a topic, whether steered or discovered."""
    if topic.signal:
        return topic.signal
    return topic.scored_signal.signal
```

Vercel DB queries should use: `LEFT JOIN scored_signals ... LEFT JOIN signals ... COALESCE(direct_signal.title, scored_signal.title)` or a similar pattern.

### Response `source` field

In the search response, `source` is a display-only string: `"rss"`, `"reddit"`, `"hn"`, `"twitter"`, or `"web"`. When creating a Signal from a web result, `source = MANUAL`. When creating from an existing DB signal, the existing signal is reused (no new Signal row needed).

### Identifying Steered Topics

Steered topics can be identified by:
- `topic.scored_signal_id IS NULL`
- `signal.source = 'manual'`

## Environment Variables

- `BRAVE_SEARCH_API_KEY` — Brave Search API key (free tier: 2,000 queries/month)

## What We Are NOT Building

- No new scoring or triage for steered topics
- No auto-generation — topics land on the dashboard for manual thesis + generation
- No pagination on research results (capped at 15, sufficient for v1)
- No rate limiting on Brave Search (2,000/month free tier is sufficient for manual use)
- No changes to the existing poller discovery flow

## Files Changed

| Layer | File | Change |
|-------|------|--------|
| Worker | `worker/app/models/signal.py` | Add `MANUAL` to `SignalSource` enum |
| Worker | `worker/app/models/topic.py` | Add nullable `signal_id` FK, make `scored_signal_id` nullable, update relationship types |
| Worker | `worker/alembic/versions/NNN_*.py` | Migration: enum value + new FK + nullable FK + backfill |
| Worker | `worker/discovery/research.py` | New: search + merge logic |
| Worker | `worker/app/main.py` | New: `/api/research` and `/api/create-topics` endpoints |
| Worker | `worker/app/config.py` | Add `brave_search_api_key` setting |
| Worker | `worker/generation/engine.py` | Add `get_signal()` helper, use in `generate_for_topic` and `generate_social_for_topic` |
| Worker | `worker/generation/thesis_suggestions.py` | Use `get_signal()` helper |
| Vercel | `app/api/research/route.ts` | New: proxy to Worker |
| Vercel | `app/api/create-topics/route.ts` | New: proxy to Worker |
| Vercel | `app/dashboard/research/page.tsx` | New: research page |
| Vercel | `components/research-results.tsx` | New: result cards with selection |
| Vercel | `lib/worker-client.ts` | Add `searchResearch()` and `createTopicsFromArticles()` |
| Vercel | `lib/db.ts` | Update joins to LEFT JOIN for scored_signals, handle nullable |
| Both | `.env.example` | Add `BRAVE_SEARCH_API_KEY` |
| Worker | `worker/discovery/test_research.py` | Tests for search + merge with mocked Brave responses |
