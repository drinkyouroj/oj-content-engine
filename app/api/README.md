# api

## Purpose

Next.js API route handlers for the approval UI. These are lightweight proxy routes that either interact with Postgres directly or forward requests to the Worker FastAPI service. All routes enforce auth via `middleware.ts`.

## Structure

| Route | Method | Purpose |
|---|---|---|
| `approve/` | POST | Approve a topic and all its drafts |
| `reject/` | POST | Reject a topic with reason and optional scoring adjustment |
| `regenerate/` | POST | Proxy to Worker — re-generate Substack draft |
| `thesis/` | POST | Save a human-provided thesis to a topic |
| `topic-action/` | POST | Snooze or kill a topic |
| `suggest-theses/` | POST | Proxy to Worker — generate thesis suggestions via Haiku |
| `generate-social/` | POST | Proxy to Worker — generate social content from Substack |
| `create-topic/` | POST | Proxy to Worker — create topic from research articles |
| `research/` | POST | Proxy to Worker — search signals DB + Brave Search |
| `health/` | GET | Proxy to Worker — health check |

## How It Fits in the Pipeline

The dashboard UI calls these routes to take actions on topics and drafts. Routes that modify data write to Postgres directly. Routes that trigger generation proxy to the Worker.

```
Dashboard UI → /app/api/* → Postgres (direct)
                           → Worker FastAPI (proxy)
```

## Authentication

All routes require one of:
- `DASHBOARD_TOKEN` query parameter
- `x-dashboard-token` request header

Auth is enforced by `middleware.ts` at the edge before routes execute.

## Environment Variables

- `DATABASE_URL` — Postgres connection string (for direct DB routes)
- `WORKER_URL` — Worker FastAPI base URL (for proxy routes)
- `WORKER_SECRET` — Shared secret sent as `x-worker-secret` to Worker
- `DASHBOARD_TOKEN` — Expected auth token

## Running Locally

Routes are served by Next.js dev server:

```bash
npm run dev
# Routes available at http://localhost:3000/api/*
```
