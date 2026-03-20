# Approval UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js dashboard for reviewing triaged topics, reading generated drafts, writing theses, and approving/rejecting content.

**Architecture:** Next.js App Router with Server Components reading from Neon Postgres directly. Simple writes (approve/reject/thesis) go direct to Postgres. Regeneration proxies to the Worker via HTTP. Token-based auth via middleware. Dark mode dashboard with sidebar navigation.

**Tech Stack:** Next.js 15, TypeScript (strict), @neondatabase/serverless, shadcn/ui, Tailwind CSS, Vitest

**Spec:** `docs/superpowers/specs/2026-03-20-approval-ui-design.md`

**Branch:** `feature/approval-ui` (from `develop`)

---

### Task 1: Next.js Project Scaffold

**Files:**
- Create: `package.json`, `next.config.ts`, `tsconfig.json`, `tailwind.config.ts`, `app/globals.css`
- Create: `app/layout.tsx`, `app/page.tsx`
- Create: `.env.local` (gitignored)
- Modify: `.gitignore`

- [ ] **Step 1: Initialize Next.js project at the repo root**

Run from the project root (`/Users/justin/CascadeProjects/oj-content-engine`):

```bash
npx create-next-app@latest . --typescript --tailwind --app --src-dir=false --import-alias="@/*" --use-npm --no-eslint
```

This will create `package.json`, `next.config.ts`, `tsconfig.json`, `tailwind.config.ts`, `app/` directory, etc. at the project root alongside the existing `worker/` directory.

If it complains about existing files, answer "yes" to proceed — it won't overwrite `worker/`, `CLAUDE.md`, or `docs/`.

- [ ] **Step 2: Initialize shadcn/ui**

```bash
npx shadcn@latest init
```

Select: New York style, Zinc base color, CSS variables. This creates `components/ui/`, `lib/utils.ts`, and updates `tailwind.config.ts`.

- [ ] **Step 3: Add required shadcn/ui components**

```bash
npx shadcn@latest add card table badge button tabs textarea dialog separator
```

- [ ] **Step 4: Install Neon serverless driver**

```bash
npm install @neondatabase/serverless
```

- [ ] **Step 5: Create .env.local**

```bash
# .env.local (not committed)
DATABASE_URL=postgresql://...  # Copy from worker/.env
DASHBOARD_TOKEN=your-secret-token-here
WORKER_URL=http://localhost:8001
WORKER_SECRET=your-worker-secret
```

- [ ] **Step 6: Update .gitignore**

Add to `.gitignore`:
```
.env.local
.env*.local
.superpowers/
```

- [ ] **Step 7: Configure dark mode in tailwind.config.ts**

Ensure `darkMode: "class"` is set. Update the theme to include brand colors:

```typescript
// In tailwind.config.ts extend.colors:
brand: {
  teal: "#00B4D8",
  orange: "#FF6B35",
}
```

- [ ] **Step 8: Update root layout with dark mode and Geist font**

`app/layout.tsx` — set `<html className="dark">`, import Geist Sans and Geist Mono fonts from `next/font/google`, set metadata title to "OJ Content Engine".

- [ ] **Step 9: Set root page to redirect to /dashboard**

`app/page.tsx` — use `redirect("/dashboard")` from `next/navigation`.

- [ ] **Step 10: Verify the app starts**

```bash
npm run dev
```

Visit `http://localhost:3000` — should redirect to `/dashboard` (which will 404 for now). The dark background should be visible.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat(approval-ui): scaffold Next.js app with shadcn/ui and Tailwind"
```

---

### Task 2: Auth Middleware + Token Helpers

**Files:**
- Create: `middleware.ts` (project root, NOT inside app/)
- Create: `lib/auth.ts`

- [ ] **Step 1: Create token validation helpers**

`lib/auth.ts` — used by API routes (Node.js runtime, has full `node:crypto`):

```typescript
import { createHmac, timingSafeEqual } from "crypto";

export const TOKEN_COOKIE = "dashboard_token";
export const TOKEN_MAX_AGE = 30 * 24 * 60 * 60; // 30 days in seconds

export function hashToken(token: string): string {
  return createHmac("sha256", token).update(token).digest("hex");
}

export function validateToken(provided: string): boolean {
  const expected = process.env.DASHBOARD_TOKEN;
  if (!expected || !provided) return false;
  const a = Buffer.from(hashToken(provided));
  const b = Buffer.from(hashToken(expected));
  return a.length === b.length && timingSafeEqual(a, b);
}

export function validateCookie(cookieValue: string): boolean {
  const expected = process.env.DASHBOARD_TOKEN;
  if (!expected || !cookieValue) return false;
  const a = Buffer.from(cookieValue);
  const b = Buffer.from(hashToken(expected));
  return a.length === b.length && timingSafeEqual(a, b);
}
```

- [ ] **Step 2: Create middleware**

`middleware.ts` (project root) — uses Web Crypto API (available in Edge Runtime):

```typescript
import { NextRequest, NextResponse } from "next/server";

const TOKEN_COOKIE = "dashboard_token";

async function sha256(input: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;

  // Skip auth for non-dashboard/api routes
  if (!pathname.startsWith("/dashboard") && !pathname.startsWith("/api")) {
    return NextResponse.next();
  }

  const token = process.env.DASHBOARD_TOKEN;
  if (!token) {
    return new NextResponse("DASHBOARD_TOKEN not configured", { status: 500 });
  }

  const expectedHash = await sha256(token);

  // Check query param token (sets cookie)
  const queryToken = searchParams.get("token");
  if (queryToken) {
    const providedHash = await sha256(queryToken);
    if (providedHash === expectedHash) {
      const url = request.nextUrl.clone();
      url.searchParams.delete("token");
      const response = NextResponse.redirect(url);
      response.cookies.set(TOKEN_COOKIE, expectedHash, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        maxAge: 30 * 24 * 60 * 60,
        path: "/",
      });
      return response;
    }
  }

  // Check header token
  const headerToken = request.headers.get("x-dashboard-token");
  if (headerToken) {
    const headerHash = await sha256(headerToken);
    if (headerHash === expectedHash) {
      return NextResponse.next();
    }
  }

  // Check cookie
  const cookie = request.cookies.get(TOKEN_COOKIE)?.value;
  if (cookie && cookie === expectedHash) {
    return NextResponse.next();
  }

  return new NextResponse("Unauthorized", { status: 401 });
}

export const config = {
  matcher: ["/dashboard/:path*", "/api/:path*"],
};
```

Uses Web Crypto API (`crypto.subtle.digest`) which is available in Next.js Edge Runtime. The `lib/auth.ts` module with HMAC-SHA256 and `timingSafeEqual` is used by API routes running in Node.js runtime.

- [ ] **Step 3: Verify auth works**

```bash
npm run dev
```

- Visit `http://localhost:3000/dashboard` → should return 401
- Visit `http://localhost:3000/dashboard?token=your-secret-token-here` → should redirect to `/dashboard` with cookie set
- Subsequent visits to `/dashboard` → should work (cookie auth)

- [ ] **Step 4: Commit**

```bash
git add middleware.ts lib/auth.ts
git commit -m "feat(approval-ui): add token-based auth middleware"
```

---

### Task 3: Database Client + Query Helpers

**Files:**
- Create: `lib/db.ts`

- [ ] **Step 1: Create Neon database client with query functions**

`lib/db.ts`:

```typescript
import { neon } from "@neondatabase/serverless";

export function getDb() {
  return neon(process.env.DATABASE_URL!);
}

// ---- Dashboard queries ----

export async function getDashboardStats() {
  const sql = getDb();
  const [reviewCount, queuedCount, draftsCount, signalsToday] =
    await Promise.all([
      sql`SELECT COUNT(*)::int AS count FROM topics WHERE status = 'review'`,
      sql`SELECT COUNT(*)::int AS count FROM topics WHERE status = 'queued'`,
      sql`SELECT COUNT(*)::int AS count FROM content_drafts WHERE status = 'draft'`,
      sql`SELECT COUNT(*)::int AS count FROM signals WHERE discovered_at > NOW() - INTERVAL '24 hours'`,
    ]);
  return {
    needReview: reviewCount[0].count,
    queued: queuedCount[0].count,
    draftsReady: draftsCount[0].count,
    signalsToday: signalsToday[0].count,
  };
}

export async function getTopicsNeedingAttention() {
  const sql = getDb();
  return sql`
    SELECT
      t.id,
      t.status,
      t.vertical,
      t.thesis_provided,
      t.created_at,
      ss.composite_score,
      ss.score_breakdown,
      s.title,
      s.url,
      s.source
    FROM topics t
    JOIN scored_signals ss ON t.scored_signal_id = ss.id
    JOIN signals s ON ss.signal_id = s.id
    WHERE t.status IN ('queued', 'review', 'generating', 'generated')
    ORDER BY ss.composite_score DESC
    LIMIT 50
  `;
}

export async function getRecentDrafts() {
  const sql = getDb();
  return sql`
    SELECT
      cd.id,
      cd.platform,
      cd.status,
      cd.notion_page_id,
      cd.created_at,
      s.title AS topic_title
    FROM content_drafts cd
    JOIN topics t ON cd.topic_id = t.id
    JOIN scored_signals ss ON t.scored_signal_id = ss.id
    JOIN signals s ON ss.signal_id = s.id
    ORDER BY cd.created_at DESC
    LIMIT 10
  `;
}

// ---- Topic review queries ----

export async function getTopicWithDetails(topicId: string) {
  const sql = getDb();
  const rows = await sql`
    SELECT
      t.*,
      ss.composite_score,
      ss.score_breakdown,
      s.title AS signal_title,
      s.url AS signal_url,
      s.source,
      s.body_preview,
      s.discovered_at
    FROM topics t
    JOIN scored_signals ss ON t.scored_signal_id = ss.id
    JOIN signals s ON ss.signal_id = s.id
    WHERE t.id = ${topicId}::uuid
  `;
  return rows[0] || null;
}

export async function getDraftsForTopic(topicId: string) {
  const sql = getDb();
  return sql`
    SELECT *
    FROM content_drafts
    WHERE topic_id = ${topicId}::uuid
    ORDER BY platform
  `;
}

// ---- Write operations ----

export async function approveTopic(topicId: string) {
  const sql = getDb();
  const drafts = await sql`
    UPDATE content_drafts SET status = 'approved'
    WHERE topic_id = ${topicId}::uuid AND status = 'draft'
    RETURNING id, notion_page_id
  `;
  await sql`
    UPDATE topics SET status = 'archived'
    WHERE id = ${topicId}::uuid
  `;
  return drafts;
}

export async function rejectTopic(
  topicId: string,
  reason: string,
  adjustment?: { keyword: string; dimension: string; delta: number }
) {
  const sql = getDb();
  await sql`
    UPDATE content_drafts SET status = 'killed'
    WHERE topic_id = ${topicId}::uuid
  `;
  await sql`
    UPDATE topics SET status = 'killed', review_decision = ${reason}
    WHERE id = ${topicId}::uuid
  `;
  if (adjustment) {
    await sql`
      INSERT INTO scoring_adjustments (id, keyword, dimension, adjustment, created_by, created_at, updated_at)
      VALUES (gen_random_uuid(), ${adjustment.keyword}, ${adjustment.dimension}, ${adjustment.delta}, 'dashboard', NOW(), NOW())
    `;
  }
}

export async function saveThesis(topicId: string, thesis: string) {
  const sql = getDb();
  await sql`
    UPDATE topics SET thesis = ${thesis}, thesis_provided = true
    WHERE id = ${topicId}::uuid
  `;
}

export async function updateTopicStatus(topicId: string, status: string) {
  const sql = getDb();
  await sql`
    UPDATE topics SET status = ${status}
    WHERE id = ${topicId}::uuid
  `;
  if (status === "killed") {
    await sql`
      UPDATE content_drafts SET status = 'killed'
      WHERE topic_id = ${topicId}::uuid
    `;
  }
}

export async function getHealthAlerts() {
  const sql = getDb();
  return sql`
    SELECT source, alert_type, consecutive_failures, last_failure_at, resolved_at
    FROM system_alerts
    WHERE resolved_at IS NULL
    ORDER BY created_at DESC
    LIMIT 20
  `;
}
```

- [ ] **Step 2: Commit**

```bash
git add lib/db.ts
git commit -m "feat(approval-ui): add Neon database client with query helpers"
```

---

### Task 4: Worker HTTP Client

**Files:**
- Create: `lib/worker-client.ts`

- [ ] **Step 1: Create Worker API client**

```typescript
// lib/worker-client.ts

export class WorkerClientError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
    this.name = "WorkerClientError";
  }
}

export async function triggerRegeneration(topicId: string): Promise<{ jobId: string }> {
  const workerUrl = process.env.WORKER_URL;
  const workerSecret = process.env.WORKER_SECRET;

  if (!workerUrl || !workerSecret) {
    throw new WorkerClientError("WORKER_URL or WORKER_SECRET not configured");
  }

  const response = await fetch(`${workerUrl}/api/regenerate/${topicId}`, {
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

  return response.json();
}
```

- [ ] **Step 2: Commit**

```bash
git add lib/worker-client.ts
git commit -m "feat(approval-ui): add Worker HTTP client for regeneration"
```

---

### Task 5: Sidebar + Dashboard Layout

**Files:**
- Create: `components/sidebar.tsx`
- Create: `app/dashboard/layout.tsx`

- [ ] **Step 1: Create sidebar component**

`components/sidebar.tsx` — a Client Component with:
- Brand logo/name "🍊 OJ Engine" at top
- Nav links: Dashboard (overview), Review Topics
- Active link highlighted with teal indicator
- Version at bottom ("v0.3.0")
- Dark background (`bg-zinc-950`), 220px wide, fixed position
- Uses `usePathname()` from `next/navigation` for active state

- [ ] **Step 2: Create dashboard layout**

`app/dashboard/layout.tsx` — Server Component:
- Sidebar on the left (fixed)
- Main content area with left padding to clear the sidebar
- Top bar with "Last poll: X ago" text (reads latest system_alert timestamp)

- [ ] **Step 3: Verify layout renders**

```bash
npm run dev
```

Visit `http://localhost:3000/dashboard?token=...` — should see sidebar with dark background.

- [ ] **Step 4: Commit**

```bash
git add components/sidebar.tsx app/dashboard/layout.tsx
git commit -m "feat(approval-ui): add sidebar navigation and dashboard layout"
```

---

### Task 6: Dashboard Overview Page

**Files:**
- Create: `components/stats-cards.tsx`
- Create: `components/topic-list.tsx`
- Create: `app/dashboard/page.tsx`

- [ ] **Step 1: Create stats cards component**

`components/stats-cards.tsx` — Server Component displaying 4 metric cards:
- Uses shadcn `Card` component
- Each card: large number + label + colored accent
- Props: `{ needReview: number, queued: number, draftsReady: number, signalsToday: number }`

- [ ] **Step 2: Create recent drafts component**

`components/recent-drafts.tsx` — Server Component showing last 10 drafts:
- Each row: platform icon (emoji: 📝 Substack, 🐦 Twitter, 💼 LinkedIn, 📷 Instagram), topic title, status badge, "Open in Notion" link if `notion_page_id` exists
- Uses shadcn `Badge` for status

- [ ] **Step 3: Create topic list component**

`components/topic-list.tsx` — Server Component with a shadcn `Table`:
- Columns: Title, Score, Status, Vertical, Thesis, Action
- Status badge uses `Badge` component with color variants (review=orange, queued=teal, generating=yellow, generated=green)
- Score is color-coded (green ≥65, yellow 55-64, red <55)
- Thesis column: checkmark or "needed" text
- Action column: "Review →" link to `/dashboard/review/[topicId]`

- [ ] **Step 4: Create dashboard page**

`app/dashboard/page.tsx` — Server Component:
- Calls `getDashboardStats()` and `getTopicsNeedingAttention()` and `getRecentDrafts()`
- Renders `<StatsCards>`, `<TopicList>`, and recent drafts section
- No loading states needed (Server Component renders on the server)

- [ ] **Step 5: Verify dashboard renders with real data**

```bash
npm run dev
```

Visit dashboard — should show stats from Neon and topic list with real topics.

- [ ] **Step 6: Commit**

```bash
git add components/stats-cards.tsx components/recent-drafts.tsx components/topic-list.tsx app/dashboard/page.tsx
git commit -m "feat(approval-ui): add dashboard overview with stats and topic list"
```

---

### Task 7: Score Breakdown Component

**Files:**
- Create: `components/score-breakdown.tsx`

- [ ] **Step 1: Create score breakdown**

`components/score-breakdown.tsx` — Server Component showing 6 horizontal bars:

```typescript
const DIMENSIONS = [
  { key: "signal_strength", label: "Signal Strength", weight: "25%" },
  { key: "brand_angle_availability", label: "Brand Angle", weight: "20%" },
  { key: "timing_window", label: "Timing Window", weight: "15%" },
  { key: "depth_potential", label: "Depth Potential", weight: "15%" },
  { key: "novelty", label: "Novelty", weight: "15%" },
  { key: "community_resonance", label: "Community Resonance", weight: "10%" },
] as const;
```

Each bar:
- Label + weight on left, score number on right
- Filled bar width = score% of container
- Color: `bg-green-500` for ≥65, `bg-yellow-500` for 55-64, `bg-red-500` for <55
- Background track: `bg-zinc-800`

- [ ] **Step 2: Commit**

```bash
git add components/score-breakdown.tsx
git commit -m "feat(approval-ui): add score breakdown visualization"
```

---

### Task 8: Draft Preview Component

**Files:**
- Create: `components/draft-preview.tsx`

- [ ] **Step 1: Create platform-specific draft renderer**

`components/draft-preview.tsx` — Server Component that renders draft content based on platform:

- **Substack:** Parse markdown headings (##), render image markers as styled info blocks, render footnotes section
- **Twitter:** Split on `[TWEET]` prefix, render each as a card with character count badge. Red badge if >280 chars.
- **LinkedIn:** Render as formatted paragraphs
- **Instagram:** Split on `---IMAGE CARD---`, render caption and image prompt as separate styled sections

Props: `{ content: string; platform: string; modelUsed?: string; notionPageId?: string; generationMetadata?: Record<string, unknown> }`

Below the content: model badge, "Open in Notion" link (if notionPageId), metadata flags.

- [ ] **Step 2: Commit**

```bash
git add components/draft-preview.tsx
git commit -m "feat(approval-ui): add platform-specific draft preview renderer"
```

---

### Task 9: Thesis Input Component

**Files:**
- Create: `components/thesis-input.tsx`

- [ ] **Step 1: Create thesis input**

`components/thesis-input.tsx` — Client Component (`"use client"`):

- If thesis not provided: shows `Textarea` + `Button` ("Save Thesis")
- On submit: `POST /api/thesis` with `{ topicId, thesis }`
- Shows loading state on button during request
- After success: switches to read-only mode showing the thesis text with "Edit" button
- If thesis already provided: shows read-only text with "Edit" button
- "Edit" toggles back to textarea mode

Props: `{ topicId: string; thesis: string | null; thesisProvided: boolean }`

- [ ] **Step 2: Commit**

```bash
git add components/thesis-input.tsx
git commit -m "feat(approval-ui): add thesis input component"
```

---

### Task 10: Topic Review Page

**Files:**
- Create: `app/dashboard/review/[topicId]/page.tsx`
- Create: `components/topic-actions.tsx`

- [ ] **Step 1: Create topic actions component**

`components/topic-actions.tsx` — Client Component (`"use client"`) with action buttons:

- Approve (green), Reject (red), Regenerate (teal), Snooze (gray), Kill (dark red)
- Each button shows spinner + disabled during request
- Reject opens a `Dialog` with reason textarea + optional scoring adjustment fields (keyword, dimension dropdown, delta slider)
- All actions call the corresponding API route, then `router.refresh()` to reload Server Component data
- Uses `useRouter()` from `next/navigation`

Props: `{ topicId: string; topicStatus: string }`

- [ ] **Step 2: Create topic review page**

`app/dashboard/review/[topicId]/page.tsx` — Server Component:

- Calls `getTopicWithDetails(topicId)` and `getDraftsForTopic(topicId)`
- Returns 404 if topic not found
- Renders:
  1. Header: title, source link, badges
  2. `<ScoreBreakdown>` with score_breakdown data
  3. `<ThesisInput>` with thesis state
  4. `<Tabs>` with one tab per platform, each containing `<DraftPreview>`
  5. `<TopicActions>` at the bottom

- [ ] **Step 3: Verify review page with real topic**

Visit `/dashboard/review/<real-topic-uuid>` — should show full review page with scores, drafts, and thesis input. Note: action buttons (Approve, Reject, etc.) will not work until Task 11 (API routes) is completed — verify visual rendering only at this stage.

- [ ] **Step 4: Commit**

```bash
git add app/dashboard/review/ components/topic-actions.tsx
git commit -m "feat(approval-ui): add topic review page with drafts and actions"
```

---

### Task 11: API Routes

**Files:**
- Create: `app/api/approve/route.ts`
- Create: `app/api/reject/route.ts`
- Create: `app/api/thesis/route.ts`
- Create: `app/api/topic-action/route.ts`
- Create: `app/api/regenerate/route.ts`
- Create: `app/api/health/route.ts`

- [ ] **Step 1: Create approve route**

`app/api/approve/route.ts`:
- Parse `{ topicId }` from body
- Call `approveTopic(topicId)` from `lib/db`
- Best-effort Notion sync: if any drafts have `notion_page_id`, update Notion page Status → "Approved" via Notion API. Catch errors, set `notionSyncFailed` flag.
- Return `{ success: true, draftsApproved: N, notionSyncFailed? }`

- [ ] **Step 2: Create reject route**

`app/api/reject/route.ts`:
- Parse `{ topicId, reason, adjustKeyword?, adjustDimension?, adjustDelta? }` from body
- Call `rejectTopic(topicId, reason, adjustment?)` from `lib/db`
- Default `adjustDimension` to `"brand_angle_availability"` if keyword provided but dimension omitted
- Best-effort Notion sync
- Return `{ success: true, notionSyncFailed? }`

- [ ] **Step 3: Create thesis route**

`app/api/thesis/route.ts`:
- Parse `{ topicId, thesis }` from body
- Call `saveThesis(topicId, thesis)` from `lib/db`
- Return `{ success: true }`

- [ ] **Step 4: Create topic-action route**

`app/api/topic-action/route.ts`:
- Parse `{ topicId, action }` from body
- Validate `action` is `"snooze"` or `"kill"`
- Call `updateTopicStatus(topicId, action === "snooze" ? "snoozed" : "killed")`
- Return `{ success: true }`

- [ ] **Step 5: Create regenerate route**

`app/api/regenerate/route.ts`:
- Parse `{ topicId }` from body
- Call `triggerRegeneration(topicId)` from `lib/worker-client`
- Return `{ success: true, jobId }`
- On WorkerClientError: return `{ success: false, error: message }` with appropriate status

- [ ] **Step 6: Create health route**

`app/api/health/route.ts`:
- Call `getHealthAlerts()` from `lib/db`
- Map DB columns to camelCase response fields
- Return `{ alerts: [...] }`

- [ ] **Step 7: Commit**

```bash
git add app/api/
git commit -m "feat(approval-ui): add API routes for approve, reject, thesis, actions, health"
```

---

### Task 12: Worker Regeneration Endpoint

**Files:**
- Modify: `worker/app/main.py`

- [ ] **Step 1: Add regeneration endpoint to FastAPI**

Add to `worker/app/main.py`. Uses the lifespan-managed `_session_factory` (not a new engine per request) and enqueues an ARQ generation job:

```python
from uuid import UUID
from fastapi import Header, HTTPException
from sqlalchemy import update as sa_update

@app.post("/api/regenerate/{topic_id}")
async def regenerate_topic(
    topic_id: UUID,
    x_worker_secret: str = Header(None),
):
    """Regenerate content for a specific topic.

    Resets topic status to 'queued' and enqueues a generation job via ARQ.
    Requires WORKER_SECRET header for authentication.

    Args:
        topic_id: UUID of the topic to regenerate.
        x_worker_secret: Shared secret for auth.

    Returns:
        Dict with status, topic_id, and job_id.
    """
    settings = get_settings()
    if not x_worker_secret or x_worker_secret != settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")

    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Worker not ready")

    from worker.app.models.topic import Topic, TopicStatus

    async with _session_factory() as session:
        await session.execute(
            sa_update(Topic).where(Topic.id == topic_id).values(status=TopicStatus.QUEUED)
        )
        await session.commit()

    # Enqueue ARQ generation job
    from arq.connections import ArqRedis, create_pool
    pool: ArqRedis = await create_pool(_redis_settings)
    job = await pool.enqueue_job("run_generation_job")
    await pool.close()

    return {"status": "queued", "topic_id": str(topic_id), "job_id": job.job_id}
```

- [ ] **Step 2: Verify endpoint works**

```bash
cd worker && python3.12 -m uvicorn worker.app.main:app --port 8001
```

Then in another terminal:
```bash
curl -X POST http://localhost:8001/api/regenerate/<topic-uuid> \
  -H "x-worker-secret: your-secret" \
  -H "Content-Type: application/json"
```

- [ ] **Step 3: Commit**

```bash
git add worker/app/main.py
git commit -m "feat(worker): add regeneration endpoint for approval UI"
```

---

### Task 13: Notion Sync Helper

**Files:**
- Create: `lib/notion-sync.ts`

- [ ] **Step 1: Create Notion status sync helper**

`lib/notion-sync.ts` — used by approve/reject API routes:

```typescript
export async function syncNotionStatus(
  notionPageIds: string[],
  status: "Approved" | "Killed"
): Promise<boolean> {
  const apiKey = process.env.NOTION_API_KEY;
  if (!apiKey || notionPageIds.length === 0) return true;

  let allSucceeded = true;

  for (const pageId of notionPageIds) {
    try {
      const response = await fetch(`https://api.notion.com/v1/pages/${pageId}`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Notion-Version": "2022-06-28",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          properties: {
            Status: { status: { name: status } },
          },
        }),
      });
      if (!response.ok) {
        console.error(`Notion sync failed for ${pageId}:`, await response.text());
        allSucceeded = false;
      }
    } catch (error) {
      console.error(`Notion sync error for ${pageId}:`, error);
      allSucceeded = false;
    }
  }

  return allSucceeded;
}
```

- [ ] **Step 2: Update approve and reject routes to use Notion sync**

Import and call `syncNotionStatus` in the approve/reject routes after Postgres updates.

- [ ] **Step 3: Commit**

```bash
git add lib/notion-sync.ts app/api/approve/route.ts app/api/reject/route.ts
git commit -m "feat(approval-ui): add best-effort Notion status sync on approve/reject"
```

---

### Task 14: Documentation + Cleanup

**Files:**
- Create: `app/README.md`
- Modify: `CHANGELOG.md`
- Modify: `.env.example`

- [ ] **Step 1: Create app README**

```markdown
# Approval UI (Next.js)

## Purpose
Dashboard for reviewing triaged topics, reading generated drafts,
writing theses, and approving/rejecting content. Implements PRD Section 7.

## Routes
- `/dashboard` — Overview with stats and topic list
- `/dashboard/review/[topicId]` — Topic review with scores, drafts, actions
- `/api/*` — approve, reject, thesis, topic-action, regenerate, health

## Running locally
npm run dev  # starts on port 3000
First visit: http://localhost:3000/dashboard?token=<DASHBOARD_TOKEN>

## Environment variables
See .env.example for all required variables.
```

- [ ] **Step 2: Update .env.example**

Add the Vercel-layer variables:
```
# Approval UI (Vercel)
DASHBOARD_TOKEN=                    # Secret token for dashboard auth
WORKER_URL=http://localhost:8001    # Worker FastAPI base URL
NOTION_API_KEY=                     # Notion integration token (for status sync)
NOTION_DB_ID=                       # Notion Second Brain database ID
```

- [ ] **Step 3: Update CHANGELOG.md**

Add under `[Unreleased]`:
```
### Added
- Approval UI: Next.js dashboard with topic review and content approval workflow
- Token-based authentication via middleware
- Dashboard overview with stats cards and topic list
- Topic review page with score breakdown, thesis input, platform draft previews
- API routes: approve, reject, thesis, topic-action, regenerate, health
- Notion status sync on approve/reject (best-effort)
- Worker regeneration endpoint
```

- [ ] **Step 4: Commit**

```bash
git add app/README.md CHANGELOG.md .env.example
git commit -m "docs(approval-ui): add README, changelog, env example updates"
```

---

### Task 15: Integration Verification

- [ ] **Step 1: Start both services**

Terminal 1 (Worker):
```bash
cd worker && python3.12 -m uvicorn worker.app.main:app --port 8001
```

Terminal 2 (Next.js):
```bash
npm run dev
```

- [ ] **Step 2: Verify dashboard loads**

Visit `http://localhost:3000/dashboard?token=<your-token>` — should show stats and topic list.

- [ ] **Step 3: Verify topic review**

Click a topic → review page should show scores, drafts across 4 platform tabs, thesis input.

- [ ] **Step 4: Test thesis submission**

Write a thesis, submit → should save and switch to read-only mode.

- [ ] **Step 5: Test approve action**

Click Approve → drafts should show "approved" status, Notion pages should update.

- [ ] **Step 6: Final commit if any fixes needed**

---

## Summary

| Task | Component | Estimated Complexity |
|------|-----------|---------------------|
| 1 | Next.js scaffold + shadcn/ui | M |
| 2 | Auth middleware + token helpers | S |
| 3 | Database client + query helpers | M |
| 4 | Worker HTTP client | S |
| 5 | Sidebar + dashboard layout | M |
| 6 | Dashboard overview page | M |
| 7 | Score breakdown component | S |
| 8 | Draft preview component | M |
| 9 | Thesis input component | S |
| 10 | Topic review page + actions | L |
| 11 | API routes (6 endpoints) | M |
| 12 | Worker regeneration endpoint | S |
| 13 | Notion sync helper | S |
| 14 | Documentation | S |
| 15 | Integration verification | S |

**Total: 15 tasks, 6 API routes, 8 components, 1 Worker endpoint**
