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
  2. Call Brave Search API for recent web articles (limit 10)
  3. Deduplicate by URL
  4. Return merged list (max 15 results)
- Output: `{ "results": [{ "title", "url", "body_preview", "source", "published_at" }] }`
- Auth: `x-worker-secret` header

**`POST /api/create-topics`**

- Input: `{ "articles": [{ "title", "url", "body_preview", "source" }] }`
- Behavior:
  1. For each article, create a `Signal` row with `source = MANUAL`
  2. Create a `Topic` row with `status = queued`, `scored_signal_id = NULL`
  3. Deduplicate against existing signals by URL (skip if already exists)
- Output: `{ "created": N, "skipped": N, "topic_ids": [...] }`
- Auth: `x-worker-secret` header

### New Vercel Routes

- `POST /api/research` — proxy to Worker `/api/research`
- `POST /api/create-topics` — proxy to Worker `/api/create-topics`

### New Vercel Page

**`/dashboard/research/page.tsx`**

- Search bar with submit button
- Loading state while searching
- Result cards showing: title, source badge (Reddit/HN/RSS/Web), URL, body preview (200 chars), published date
- Checkbox selection on each card
- "Create N Topics" button (disabled when none selected)
- Success state: "Created N topics" with link back to dashboard

### Worker Module

**`worker/discovery/research.py`**

- `search_existing_signals(query, session, limit=10)` — `ILIKE` search on signals table
- `search_web(query, api_key, limit=10)` — Brave Search API call via httpx
- `merge_and_deduplicate(db_results, web_results, max_results=15)` — deduplicate by URL, prefer DB results

## Data Model Changes

### `SignalSource` Enum

Add `MANUAL = "manual"` to the existing enum in `worker/app/models/signal.py`.

Requires Alembic migration to add the enum value to Postgres.

### `topics.scored_signal_id`

Make nullable. Currently a required FK to `scored_signals.id`. Steered topics have `scored_signal_id = NULL` since they skip scoring.

Requires Alembic migration to alter the column.

### Identifying Steered Topics

Steered topics can be identified by either:
- `signal.source = 'manual'` (via the signal FK)
- `topic.scored_signal_id IS NULL`

The review page already handles missing scores gracefully (shows "—").

## Environment Variables

- `BRAVE_SEARCH_API_KEY` — Brave Search API key (free tier: 2,000 queries/month)

## What We Are NOT Building

- No new scoring or triage for steered topics
- No auto-generation — topics land on the dashboard for manual thesis + generation
- No new database tables — reuses `signals` and `topics`
- No changes to the existing poller discovery flow

## Files Changed

| Layer | File | Change |
|-------|------|--------|
| Worker | `worker/app/models/signal.py` | Add `MANUAL` to `SignalSource` enum |
| Worker | `worker/app/models/topic.py` | Make `scored_signal_id` nullable |
| Worker | `worker/alembic/versions/NNN_*.py` | Migration for enum + nullable FK |
| Worker | `worker/discovery/research.py` | New: search + merge logic |
| Worker | `worker/app/main.py` | New: `/api/research` and `/api/create-topics` endpoints |
| Worker | `worker/app/config.py` | Add `brave_search_api_key` setting |
| Vercel | `app/api/research/route.ts` | New: proxy to Worker |
| Vercel | `app/api/create-topics/route.ts` | New: proxy to Worker |
| Vercel | `app/dashboard/research/page.tsx` | New: research page |
| Vercel | `components/research-results.tsx` | New: result cards with selection |
| Vercel | `lib/worker-client.ts` | Add `searchResearch()` and `createTopicsFromArticles()` |
| Vercel | `lib/db.ts` | Update queries to handle nullable `scored_signal_id` |
| Both | `.env.example` | Add `BRAVE_SEARCH_API_KEY` |
