# 002 — Upstash Redis Over Self-Hosted Redis
_Date: 2026-03-19 | Status: Accepted_

## Context

The pipeline needs Redis for two purposes: (1) ARQ task queue backend for the worker,
and (2) pub/sub notifications between pipeline stages and the Vercel UI (notification
badges, real-time updates). Both the Vercel layer and the Worker layer need access.

## Options Considered

1. **Self-hosted Redis (on Worker host or separate container)** — Run a Redis instance
   on Railway/Fly.io alongside the worker.
   - Pros: Full Redis feature set, no per-request costs, complete control
   - Cons: Another container to manage. Vercel Functions can't connect to arbitrary
     Redis instances without public exposure or VPN. Backup/HA is on us.
     Overkill for the expected throughput (~50 signals/day).

2. **Upstash Redis (serverless, Vercel-native)** — Use Upstash's serverless Redis with
   REST API. Native Vercel Marketplace integration.
   - Pros: Works from both Vercel Functions (REST API) and Worker (standard Redis
     protocol). Auto-provisioned env vars via Vercel Marketplace. No container to
     manage. Built-in persistence. Pay-per-request pricing is negligible at our scale.
   - Cons: REST API adds ~1-5ms latency vs. direct Redis. Some advanced Redis features
     may be unavailable. Vendor lock-in (mitigated by standard Redis protocol on
     worker side).

3. **Skip Redis entirely — use Postgres for everything** — Use Postgres LISTEN/NOTIFY
   for pub/sub and a polling-based queue for ARQ.
   - Pros: One fewer dependency. Postgres can handle pub/sub at low scale.
   - Cons: ARQ requires Redis — it's a hard dependency. Postgres LISTEN/NOTIFY doesn't
     persist messages, so missed notifications are lost. Would need to replace ARQ with
     a Postgres-based queue (more custom code).

## Decision

Option 2: Upstash Redis. ARQ requires Redis (non-negotiable). Upstash provides both
standard Redis protocol (for ARQ on the worker) and REST API (for Vercel Functions).
The Vercel Marketplace integration auto-provisions credentials. At ~50 signals/day,
the cost is effectively zero.

## Consequences

- **Easier:** Zero Redis ops. Both hosts connect without networking gymnastics.
  Vercel Marketplace handles credential provisioning.
- **Harder:** Slight latency overhead on the REST API path (Vercel side). Need to
  be mindful of Upstash's per-request pricing if throughput grows significantly.
- **Deferred:** If throughput exceeds Upstash's free/affordable tier, revisit
  self-hosted Redis with a proper VPN setup. Not expected before v2.0.
