# Approval UI (Next.js)

## Purpose
Dashboard for reviewing triaged topics, reading generated drafts,
writing theses, and approving/rejecting content. Implements PRD Section 7.

## Routes
- `/dashboard` — Overview with stats and topic list
- `/dashboard/review/[topicId]` — Topic review with scores, drafts, actions
- `/api/approve` — POST: approve all drafts for a topic
- `/api/reject` — POST: reject with reason + optional scoring adjustment
- `/api/thesis` — POST: save thesis for a topic
- `/api/topic-action` — POST: snooze or kill topic
- `/api/regenerate` — POST: trigger Worker to re-generate drafts
- `/api/health` — GET: system alerts / poller status

## Running locally
```bash
npm run dev  # starts on port 3000
```
First visit: `http://localhost:3000/dashboard?token=<DASHBOARD_TOKEN>`

## Environment variables
See .env.example for all required variables.

## Tech Stack
- Next.js 15 (App Router) + TypeScript (strict)
- shadcn/ui + Tailwind CSS (dark mode)
- @neondatabase/serverless (direct Postgres queries)
- Token-based auth via middleware
