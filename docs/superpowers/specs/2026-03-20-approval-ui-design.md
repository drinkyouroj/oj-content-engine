# Approval UI Design

**Goal:** Build a Next.js dashboard for reviewing triaged topics, reading generated drafts, writing theses, and approving/rejecting content before publication.

**Scope:** PRD Tasks 15-19 (Next.js scaffold, topic review, thesis injection, exemplar management deferred, health dashboard minimal). Vercel layer only — one new Worker endpoint for regeneration.

**Depends on:** Waves 1-3 (infrastructure, discovery, scoring, triage) and Wave 4a (content generation, Notion staging).

---

## 1. Architecture

### Two-Layer Integration

The approval UI is the Vercel layer of the two-host architecture defined in CLAUDE.md:

- **Reads:** Next.js Server Components query Neon Postgres directly via `@neondatabase/serverless`. No dependency on the Worker for page loads.
- **Simple writes:** API routes update Postgres directly for approve, reject, thesis, snooze, kill actions. These are status updates that don't require LLM work.
- **LLM writes:** Regeneration triggers the Worker via HTTP. The Worker enqueues an ARQ generation job. This requires one new FastAPI endpoint on the Worker.

### Tech Stack

| Technology | Purpose |
|------------|---------|
| Next.js 15 (App Router) | Server Components, API routes, middleware |
| `@neondatabase/serverless` | Direct Postgres queries from Server Components |
| shadcn/ui + Tailwind CSS | Component library + styling |
| TypeScript (strict) | Type safety, no `any` |

---

## 2. Authentication

Simple token-based auth — no user management, no sessions table.

- `DASHBOARD_TOKEN` environment variable holds a secret string
- Next.js middleware checks all `/dashboard` and `/api` routes
- Token accepted via:
  - Query param: `?token=<secret>` (sets HTTP-only cookie for 30 days)
  - Header: `x-dashboard-token: <secret>` (for programmatic API access)
  - Cookie: `dashboard_token` (set automatically on first query-param auth)
- Cookie contains a SHA-256 HMAC of the token (keyed with itself — acceptable for single-user threat model), validated against the env var
- No login page — first visit with `?token=` authenticates and redirects

---

## 3. Project Structure

The Next.js app lives at the project root alongside the existing `worker/` directory:

```
oj-content-engine/
├── middleware.ts                  # Token auth check (must be at project root for Next.js)
├── app/
│   ├── layout.tsx                # Root layout (fonts, global styles)
│   ├── page.tsx                  # Redirect to /dashboard
│   ├── dashboard/
│   │   ├── layout.tsx            # Dashboard layout with sidebar
│   │   ├── page.tsx              # Overview: stats, topic list
│   │   └── review/
│   │       └── [topicId]/
│   │           └── page.tsx      # Topic review: scores, drafts, actions
│   └── api/
│       ├── approve/route.ts      # POST: approve draft
│       ├── reject/route.ts       # POST: reject draft + optional scoring_adjustment
│       ├── regenerate/route.ts   # POST: proxy to Worker for re-generation
│       ├── thesis/route.ts       # POST: save thesis for topic
│       ├── topic-action/route.ts # POST: snooze or kill topic
│       └── health/route.ts       # GET: system alerts / poller status
├── lib/
│   ├── db.ts                     # Neon serverless client + query helpers
│   ├── auth.ts                   # Token validation helpers
│   └── worker-client.ts          # HTTP client for Worker API calls
├── components/
│   ├── ui/                       # shadcn/ui components (auto-generated)
│   ├── sidebar.tsx               # Persistent sidebar navigation
│   ├── stats-cards.tsx           # Dashboard stat cards (4 metrics)
│   ├── topic-list.tsx            # Topic table with status/vertical badges
│   ├── score-breakdown.tsx       # 6-dimension horizontal bar chart
│   ├── draft-preview.tsx         # Platform-specific content rendering
│   └── thesis-input.tsx          # Thesis text area + submit
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── .env.local                    # Local env vars (not committed)
├── worker/                       # Existing Python worker (unchanged)
└── ...
```

---

## 4. Dashboard Overview (`/dashboard`)

Server Component — all data loaded server-side from Neon.

### Stats Bar

Four cards across the top:

| Card | Color | Query |
|------|-------|-------|
| Need Review | Orange (#FF6B35) | `COUNT(*) FROM topics WHERE status = 'review'` |
| Queued | Teal (#00B4D8) | `COUNT(*) FROM topics WHERE status = 'queued'` |
| Drafts Ready | Green | `COUNT(*) FROM content_drafts WHERE status = 'draft'` |
| Signals Today | Gray | `COUNT(*) FROM signals WHERE discovered_at > NOW() - INTERVAL '24 hours'` |

### Topics Needing Attention

Table of topics with status in (`queued`, `review`, `generating`, `generated`), sorted by composite score descending. Columns:

- Title (from `signals.title` via `scored_signals` join)
- Composite score (number, color-coded)
- Status badge (color-coded pill)
- Vertical badge
- Thesis (checkmark if provided, "needed" if not)
- Link → `/dashboard/review/[topicId]`

### Recent Drafts

Last 10 content drafts showing:
- Platform icon (Substack/Twitter/LinkedIn/Instagram)
- Topic title
- Status badge
- "Open in Notion" link (if `notion_page_id` exists)

---

## 5. Topic Review Page (`/dashboard/review/[topicId]`)

Server Component with Client Component islands for interactive elements.

### Header

- Topic title (h1), source URL link, discovered date
- Status badge, vertical badge, composite score (large number)

### Score Breakdown Panel

Six horizontal bars, one per scoring dimension:
- Signal Strength (25%), Timing Window (15%), Depth Potential (15%), Novelty (15%), Community Resonance (10%), Brand Angle (20%)
- Bar width proportional to score (0-100)
- Color: green ≥ 65, yellow 55-64, red < 55
- Weight percentage shown next to label

### Thesis Input (Client Component)

Shown if `thesis_provided = false`:
- Text area with placeholder: "What's your take? 2-3 sentences"
- Submit button → `POST /api/thesis`
- After submission: shows thesis as read-only text with "Edit" button
- If thesis already provided: shows read-only text

### Platform Drafts (Tabbed)

Tabs: Substack | Twitter | LinkedIn | Instagram

Each tab renders the draft content appropriately:
- **Substack:** Markdown → HTML with heading hierarchy, image markers displayed as styled blocks
- **Twitter:** Thread view — each `[TWEET]` block rendered as a card with character count
- **LinkedIn:** Formatted post text
- **Instagram:** Caption section + image card prompt section (visually separated)

Below each draft:
- Model used, token count badge
- "Open in Notion" button (if `notion_page_id` exists)
- Generation metadata flags (AI-originated, voice-drift applied, etc.)

### Action Buttons

Bottom of page, full width:

| Button | Color | Action |
|--------|-------|--------|
| Approve | Green | `POST /api/approve` — sets all drafts status → approved, topic status → archived |
| Reject | Red | Opens reason dialog (reason + optional scoring adjustment), `POST /api/reject` — sets drafts status → killed |
| Regenerate | Teal | `POST /api/regenerate` — triggers Worker ARQ job |
| Snooze 24h | Gray | `POST /api/topic-action` with action=snooze — sets topic status → snoozed |
| Kill Topic | Dark red | `POST /api/topic-action` with action=kill — sets topic status → killed |

All buttons show a loading spinner and disable during the async request.

Approve and Reject sync Notion page status as best-effort — if the Notion API call fails, the Postgres update still succeeds and a warning is returned in the response. Postgres is always the source of truth for status.

---

## 6. API Routes

### Direct Postgres Writes

**`POST /api/approve`**
- Body: `{ topicId: string }`
- Updates: `content_drafts.status → 'approved'` for all drafts of this topic
- Updates: `topics.status → 'archived'` (approved topics are archived — the content lives on in drafts and Notion)
- Best-effort: updates Notion page Status → "Approved" (if notion_page_id exists). Notion failure does not block the Postgres update — a `notionSyncFailed: true` flag is included in the response.
- Returns: `{ success: true, draftsApproved: N, notionSyncFailed?: boolean }`

**`POST /api/reject`**
- Body: `{ topicId: string, reason: string, adjustKeyword?: string, adjustDimension?: string, adjustDelta?: number }`
- Updates: `content_drafts.status → 'killed'`, `topics.review_decision → reason`, `topics.status → 'killed'`
- Optional: creates `scoring_adjustments` row if adjustKeyword provided. `adjustDimension` defaults to `"brand_angle_availability"` if omitted (most common rejection reason is off-brand). Valid dimensions: signal_strength, timing_window, depth_potential, novelty, community_resonance, brand_angle_availability.
- Best-effort: updates Notion page Status → "Killed" (same best-effort pattern as approve).
- Returns: `{ success: true, notionSyncFailed?: boolean }`

**`POST /api/thesis`**
- Body: `{ topicId: string, thesis: string }`
- Updates: `topics.thesis → thesis`, `topics.thesis_provided → true`
- Returns: `{ success: true }`

**`POST /api/topic-action`**
- Body: `{ topicId: string, action: "snooze" | "kill" }`
- Snooze: sets `topics.status → 'snoozed'`
- Kill: sets `topics.status → 'killed'`, also sets `content_drafts.status → 'killed'` for all drafts
- Returns: `{ success: true }`

**`GET /api/health`**
- Reads from `system_alerts` table
- Returns: `{ alerts: [{ source, alertType, consecutiveFailures, lastFailureAt, resolvedAt }] }`
- Field mapping from database columns: `alert_type → alertType`, `consecutive_failures → consecutiveFailures`, `last_failure_at → lastFailureAt` (ISO-8601), `resolved_at → resolvedAt` (ISO-8601 or null)
- Active alerts: `resolved_at IS NULL`

### Worker Proxy

**`POST /api/regenerate`**
- Body: `{ topicId: string }`
- Calls: `POST {WORKER_URL}/api/regenerate/{topicId}` with `WORKER_SECRET` header
- Worker enqueues ARQ generation job for that specific topic
- Returns: `{ success: true, jobId: string }`

### Worker-Side Addition

One new FastAPI endpoint on the Worker:

```python
# worker/app/main.py
@app.post("/api/regenerate/{topic_id}")
async def regenerate_topic(topic_id: UUID, request: Request):
    # Verify WORKER_SECRET header
    # Reset topic.status → queued
    # Enqueue run_generation_job via ARQ
    # Return job ID
```

---

## 7. Database Access (`lib/db.ts`)

Uses `@neondatabase/serverless` with the `neon()` SQL tagged template:

```typescript
import { neon } from '@neondatabase/serverless';

const sql = neon(process.env.DATABASE_URL!);

export async function getTopicsNeedingReview() {
  return sql`
    SELECT t.*, ss.composite_score, ss.score_breakdown, s.title, s.url
    FROM topics t
    JOIN scored_signals ss ON t.scored_signal_id = ss.id
    JOIN signals s ON ss.signal_id = s.id
    WHERE t.status IN ('queued', 'review', 'generating', 'generated')
    ORDER BY ss.composite_score DESC
  `;
}
```

No ORM — raw SQL queries for reads. The Neon serverless driver handles connection pooling and is designed for serverless environments.

---

## 8. Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `DATABASE_URL` | Neon Postgres connection string | Yes |
| `DASHBOARD_TOKEN` | Auth token for dashboard access | Yes |
| `WORKER_URL` | Worker FastAPI base URL (e.g., http://localhost:8001) | Yes (for regenerate) |
| `WORKER_SECRET` | Shared secret for Worker API auth | Yes (for regenerate) |
| `NOTION_API_KEY` | Notion integration token (for status sync on approve/reject) | Optional |
| `NOTION_DB_ID` | Notion database ID | Optional |

---

## 9. Design System

- **Dark mode** by default (zinc/neutral palette)
- **Brand colors:** Teal (#00B4D8) for primary actions, Orange (#FF6B35) for attention/warnings
- **Font:** Geist Sans (system) for UI, Geist Mono for scores/IDs/code
- **shadcn/ui components used:** Card, Table, Badge, Button, Tabs, Textarea, Dialog, Separator
- **Sidebar:** Fixed left, 220px wide, dark background, teal active indicator

---

## 10. Testing Strategy

| Layer | What | Framework |
|-------|------|-----------|
| API routes | Unit tests for each route handler with mocked DB | Vitest |
| Components | Render tests for score breakdown, draft preview, thesis input | Vitest + Testing Library |
| Auth middleware | Token validation, cookie setting, rejection | Vitest |
| DB queries | Query structure tests against mock data | Vitest |

Test files live alongside source: `route.test.ts`, `component.test.tsx`.

---

## 11. Scope Boundaries

**In scope (v0.3.0):**
- Dashboard overview with stats and topic list
- Topic review page with scores, drafts, thesis input, actions
- API routes for approve, reject, regenerate, thesis, health
- Simple token auth
- Notion status sync on approve/reject

**Deliberate simplifications:**
- PRD's `/dashboard/content/[draftId]` (separate draft preview page) is folded into the topic review page as tabbed platform drafts. No separate route needed.

**Deferred:**
- Voice exemplar management page (seeded via script, rarely changes)
- Full health dashboard (minimal health via API route only)
- Draft-level actions (approve/reject individual platforms — v0.3.0 approves all or none)
- Notion bidirectional sync (Notion → Postgres status changes)
- Real-time updates / WebSocket notifications
