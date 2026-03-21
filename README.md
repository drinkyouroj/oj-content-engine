# OJ Content Engine

Automated content creation pipeline for the drinkYourOJ brand. Discovers trends from RSS, Reddit/HN; scores and triages against a brand rubric; generates platform-specific content (Substack, Twitter/X, LinkedIn, Instagram); stages drafts in Notion; publishes after human approval.

## Quick Start

See [docs/runbooks/local-dev-setup.md](docs/runbooks/local-dev-setup.md) for full local development setup instructions.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the system diagram and data flow.

## PRD

The PRD is the source of truth for what gets built: [output/PRD.md](output/PRD.md).

## Tech Stack

- **Vercel Layer:** Next.js (App Router) — approval UI, lightweight API routes
- **Worker Layer:** FastAPI + ARQ (Docker, deployed on Railway) — discovery, scoring, generation, Notion staging
- **Database:** Neon Postgres (shared between layers)
- **Queue/Pub-Sub:** Upstash Redis (shared between layers)

## Documentation

See [docs/](docs/) for architecture diagrams, decision records, runbooks, and API reference.
