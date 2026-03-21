# Architecture

_Last updated: 2026-03-19 | PRD Section 1_

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  WORKER HOST (Railway / Fly.io)                                     │
│  FastAPI + ARQ (async task queue) + Docker                          │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │
│  │ Stage 1  │──>│ Stage 2  │──>│ Stage 3  │──>│ Stage 3.5        │ │
│  │Discovery │   │ Scoring  │   │ Triage   │   │ Thesis Read      │ │
│  │          │   │          │   │          │   │ (reads from DB)  │ │
│  │ RSS      │   │ Pass 1:  │   │ Hard     │   └────────┬─────────┘ │
│  │ Reddit   │   │  Rules   │   │ gates +  │            │           │
│  │ HN       │   │ Pass 2:  │   │ thresholds            ▼           │
│  │ Twitter  │   │  Haiku   │   │          │   ┌──────────────────┐ │
│  └──────────┘   └──────────┘   └──────────┘   │ Stage 4          │ │
│                                                │ Content Gen      │ │
│                                                │ (Sonnet)         │ │
│                                                │                  │ │
│                                                │ 4 platform       │ │
│                                                │ branches:        │ │
│                                                │ Substack         │ │
│                                                │ Twitter/X        │ │
│                                                │ LinkedIn         │ │
│                                                │ Instagram        │ │
│                                                └────────┬─────────┘ │
│                                                         │           │
│                                                         ▼           │
│                                                ┌──────────────────┐ │
│                                                │ Stage 5          │ │
│                                                │ Notion Staging   │ │
│                                                │ (page creation)  │ │
│                                                └──────────────────┘ │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Shared: Neon Postgres + Upstash Redis                         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ shared Postgres + Redis
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│  VERCEL (Next.js App Router)                                        │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │ Stage 5      │  │ Stage 6      │  │ Stage 3.5               │   │
│  │ Notion Read  │  │ Approval UI  │  │ Thesis Input UI         │   │
│  │ (fallback)   │  │ /dashboard/* │  │ /dashboard/review/[id]  │   │
│  └──────────────┘  └──────────────┘  └─────────────────────────┘   │
│                                                                     │
│  Routes:                                                            │
│  /dashboard              — overview, badges, health                 │
│  /dashboard/review/[id]  — topic review + thesis input              │
│  /api/approve            — POST: approve draft                      │
│  /api/reject             — POST: reject draft                       │
│  /api/regenerate         — POST: trigger re-generation              │
│  /api/thesis             — POST: save thesis                        │
│  /api/health             — GET: system health                       │
│                                                                     │
│  Hard limit: NO long-running ops (≤60s max)                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
RSS/Reddit/HN/Twitter
        │
        ▼
  signals table (Postgres)
        │
        ▼ Redis pub/sub notification
  scored_signals table (rule-based + LLM scoring)
        │
        ▼
  topics table (triage: queued / review / archived)
        │
        ├── thesis provided? ──> topics.thesis column
        │
        ▼
  content_drafts table (per-platform drafts)
        │
        ▼
  Notion pages (staged for review)
        │
        ▼
  Approval UI (approve / reject / regenerate)
        │
        ▼
  Published (manual or automated)
```

## Database Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `signals` | Raw discovered trends | source, url, title, dedup_hash, source_metrics |
| `scored_signals` | Signals after scoring | score_breakdown (JSONB), composite_score |
| `topics` | Triaged topics | status, thesis, queued_at, review_decision |
| `content_drafts` | Generated platform content | platform, content, status, notion_page_id |
| `voice_exemplars` | Brand voice reference posts | content, platform, active |
| `scoring_adjustments` | Justin's per-keyword tweaks | keyword, dimension, adjustment (-20 to +20) |
| `system_alerts` | Poller health monitoring | source, alert_type, consecutive_failures |

## Key Boundaries

- **Worker → Vercel communication:** Shared Postgres + Upstash Redis pub/sub
- **Vercel → Worker triggers:** POST to Worker HTTP endpoints (authenticated with `WORKER_SECRET`)
- **LLM usage:** Haiku for scoring (~$0.006/day), Sonnet for generation (~$0.08/topic)
- **External APIs:** Notion (3 req/s limit), Twitter v2 (Basic tier), Reddit JSON, HN Algolia
