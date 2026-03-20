# 004 — No Local Dev Containers for Postgres/Redis
_Date: 2026-03-19 | Status: Accepted_

## Context

For local development, should docker-compose include local Postgres and
Redis containers, or should developers connect to the external Neon and
Upstash services?

## Options Considered

1. **Local containers** — docker-compose includes Postgres + Redis.
   - Pros: Fully offline development. No cloud costs during dev.
     Fast iteration (no network latency to cloud).
   - Cons: Schema drift risk (local Postgres may diverge from Neon).
     Need to seed data. Extra containers to manage. Doesn't test
     real connection behavior (Neon's serverless driver, Upstash REST).

2. **External only** — docker-compose runs Worker only, connects to Neon + Upstash.
   - Pros: Dev environment matches production exactly. No schema drift.
     Neon free tier is generous. Upstash free tier handles dev load.
     Tests real network behavior.
   - Cons: Requires internet. Cloud services must be provisioned.
     Slightly slower queries (network latency).

## Decision

Option 2: External only. Justin prefers developing against real services.
Neon's free tier provides branching (can create a dev branch), and Upstash's
free tier handles the minimal dev load. This eliminates an entire class of
"works locally but breaks in production" bugs.

## Consequences

- **Easier:** One fewer thing to configure. Dev behavior matches prod.
  Neon branching provides isolated dev databases without containers.
- **Harder:** Must have internet to develop. Need to provision Neon +
  Upstash before first dev session.
- **Deferred:** Can add local containers later if offline dev becomes
  necessary (e.g., travel, unreliable internet).
