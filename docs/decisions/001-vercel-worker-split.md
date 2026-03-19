# 001 — Two-Host Split: Vercel + Worker
_Date: 2026-03-19 | Status: Accepted_

## Context

The content pipeline needs to run long-running operations (RSS polling, LLM generation,
Playwright automation) alongside a lightweight approval UI. These have fundamentally
different runtime requirements.

## Options Considered

1. **Vercel-only (Next.js + Vercel Functions)** — Run everything on Vercel using serverless
   functions and cron jobs.
   - Pros: Single deployment target, simpler ops, native integrations
   - Cons: Hard 10-60s function timeout kills polling and generation (30-120s per platform).
     No Docker for Playwright. Would require splitting LLM calls into micro-steps with
     queue-based chaining — over-engineered for a solo dev.

2. **Worker-only (FastAPI on Railway/Fly.io)** — Run everything on the worker host,
   including the approval UI.
   - Pros: No timeout limits, full Docker support, single host
   - Cons: No SSR/React ecosystem for the dashboard. Would need to build a separate
     frontend or use a template engine. Loses Vercel's edge network, preview deploys,
     and native Postgres/Redis integrations.

3. **Two-host split: Vercel (UI + lightweight API) + Worker (long-running ops)** — Vercel
   handles the approval UI and reads from shared Postgres/Redis. Worker handles discovery,
   scoring, generation, and Notion writes.
   - Pros: Each host plays to its strengths. Vercel gets fast SSR dashboard with zero
     timeout concerns. Worker gets unlimited runtime + Docker. Shared Postgres keeps data
     in one place.
   - Cons: Two deployment targets to manage. Need a shared secret for Vercel → Worker calls.
     Slightly more complex local dev (run both services).

## Decision

Option 3: Two-host split. The timeout constraint on Vercel is a hard blocker for polling
and generation. Running a React dashboard on a pure Python worker is awkward. The split
maps cleanly to the pipeline's natural boundaries: long-running data processing vs.
lightweight human review interface.

## Consequences

- **Easier:** Each host has a clear responsibility. Vercel ops are standard Next.js.
  Worker ops are standard FastAPI + Docker.
- **Harder:** Local development requires running both services. Need to keep shared
  database schemas in sync across both codebases.
- **Deferred:** Could revisit if Vercel lifts timeout limits significantly or if the
  worker needs its own UI (e.g., admin panel for ARQ job monitoring).
