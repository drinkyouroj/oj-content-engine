# Infrastructure Scaffold Design

_Date: 2026-03-19 | Branch: `feature/infra` | PRD Tasks: 1, 2_

## Purpose

Set up the foundational Worker layer: Postgres schema (all 7 tables from the PRD),
FastAPI application, ARQ task queue, Docker container, and Alembic migrations. This
is the base that all subsequent feature branches build on.

## Decisions Made

| Decision | Choice | Rationale | Decision Doc |
|----------|--------|-----------|--------------|
| Python version | 3.12 | User preference | — |
| Migration tool | Alembic | Autogenerate from SQLAlchemy models, proper up/down | — |
| ORM | SQLAlchemy (full async ORM) | Alembic autogenerate, Pythonic queries, handles JSONB well | `docs/decisions/003-sqlalchemy-orm.md` |
| Worker host | Railway | User preference | — |
| Local dev DB | External only (Neon + Upstash) | No local containers; dev against real services | `docs/decisions/004-no-local-dev-containers.md` |
| ARQ scaffold | Minimal (config + 1 example job) | Avoids merge conflicts when parallel branches register jobs | — |
| Column types | ENUM over TEXT for constrained values | Type safety at DB level; PRD uses TEXT but ENUMs prevent invalid data | — |

## Directory Structure

```
worker/
├── alembic/
│   ├── env.py                           # Async Alembic config
│   ├── script.py.mako                   # Migration template
│   └── versions/
│       └── 001_initial_schema.py        # All 7 tables
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app + /health endpoint
│   ├── config.py                        # pydantic-settings (env vars)
│   ├── database.py                      # Async engine + session factory
│   └── models/
│       ├── __init__.py                  # Re-exports all models
│       ├── base.py                      # DeclarativeBase + timestamp mixin
│       ├── signal.py                    # Signal
│       ├── scored_signal.py             # ScoredSignal
│       ├── topic.py                     # Topic
│       ├── content_draft.py             # ContentDraft
│       ├── voice_exemplar.py            # VoiceExemplar
│       ├── scoring_adjustment.py        # ScoringAdjustment
│       └── system_alert.py             # SystemAlert
├── jobs/
│   ├── __init__.py
│   ├── worker.py                        # ARQ WorkerSettings + example job
│   └── README.md
├── app/README.md                        # App module overview
├── conftest.py                          # Shared pytest fixtures
├── alembic.ini
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh                        # Runs uvicorn + ARQ worker
└── README.md
```

One model per file to minimize merge conflicts when parallel feature branches
touch different pipeline stages.

## Database Schema

All tables use UUID primary keys and `created_at`/`updated_at` timestamp columns
via a shared mixin.

### `signals` (PRD Section 2)

Raw discovered trends from all sources.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `source` | ENUM | NOT NULL | rss, reddit, hn, twitter |
| `url` | TEXT | NOT NULL | Source URL |
| `title` | TEXT | NOT NULL | Signal title |
| `body_preview` | TEXT | | First 500 chars |
| `discovered_at` | TIMESTAMPTZ | NOT NULL | When the poller found it |
| `source_metrics` | JSONB | | Upvotes, comments, shares, velocity |
| `dedup_hash` | TEXT | UNIQUE, NOT NULL | SHA-256 of normalized URL |

### `scored_signals` (PRD Section 3)

Signals after two-pass scoring.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `signal_id` | UUID | FK → signals.id, NOT NULL | |
| `score_breakdown` | JSONB | NOT NULL | Per-dimension scores (see structure below) |
| `composite_score` | NUMERIC | NOT NULL | Weighted composite 0-100 |
| `status` | ENUM | NOT NULL, DEFAULT 'pending' | pending, scored, failed |
| `pass1_completed_at` | TIMESTAMPTZ | | Rule-based pass |
| `pass2_completed_at` | TIMESTAMPTZ | | LLM pass |

**`score_breakdown` JSONB structure** (PRD Section 3, all values 0-100):
```json
{
  "signal_strength": 70,
  "timing_window": 50,
  "depth_potential": 80,
  "novelty": 60,
  "community_resonance": 40,
  "brand_angle_availability": 85
}
```
Application-level validation ensures all 6 keys are present before setting
`status` to `scored`.

### `topics` (PRD Section 3, 3.5)

Triaged topics awaiting thesis injection and/or generation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `scored_signal_id` | UUID | FK → scored_signals.id, NOT NULL | |
| `status` | ENUM | NOT NULL | queued, review, generating, generated, snoozed, archived, killed |
| `thesis` | TEXT | | Justin's 2-3 sentence take |
| `thesis_provided` | BOOLEAN | DEFAULT false | |
| `queued_at` | TIMESTAMPTZ | | |
| `reviewed_by` | TEXT | | |
| `review_decision` | TEXT | | |

### `content_drafts` (PRD Section 4, 5)

Per-platform generated content.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `topic_id` | UUID | FK → topics.id, NOT NULL | |
| `platform` | ENUM | NOT NULL | substack, twitter, linkedin, instagram |
| `content` | TEXT | NOT NULL | Generated draft body |
| `status` | ENUM | NOT NULL, DEFAULT 'draft' | draft, review, approved, published, killed |
| `notion_page_id` | TEXT | | Notion page URL/ID |
| `model_used` | TEXT | | e.g. claude-sonnet-4-5 |
| `token_cost` | NUMERIC | | Approximate USD cost |
| `image_url` | TEXT | | Instagram image card URL |
| `generated_at` | TIMESTAMPTZ | | |

### `voice_exemplars` (PRD Section 4)

Curated brand voice reference posts. 10-15 posts, 3-5 randomly selected per generation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `content` | TEXT | NOT NULL | Exemplar post text |
| `platform` | ENUM | NOT NULL | substack, twitter, linkedin, instagram |
| `active` | BOOLEAN | DEFAULT true | |

### `scoring_adjustments` (PRD Section 3)

Justin's per-keyword scoring tweaks from the review UI.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `keyword` | TEXT | NOT NULL | Keyword or topic to adjust |
| `dimension` | TEXT | NOT NULL | Which scoring dimension |
| `adjustment` | INTEGER | NOT NULL, CHECK -20..+20 | |
| `created_by` | TEXT | | |

### `system_alerts` (PRD Section 2)

Poller health monitoring.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `source` | TEXT | NOT NULL | Which poller |
| `alert_type` | TEXT | NOT NULL | e.g. consecutive_failures |
| `consecutive_failures` | INTEGER | DEFAULT 0 | |
| `last_failure_at` | TIMESTAMPTZ | | |
| `resolved_at` | TIMESTAMPTZ | | Null if unresolved |

## Worker Application

### FastAPI (`app/main.py`)

- Single `/health` GET endpoint returning DB connectivity, Redis connectivity, worker status
- Lifespan handler: creates/closes async SQLAlchemy engine and Redis pool on startup/shutdown
- No auth on health endpoint (Railway hits it directly)

### Config (`app/config.py`)

`pydantic-settings` `BaseSettings` class reading from env vars:

```python
class Settings(BaseSettings):
    database_url: str                    # Neon Postgres connection string
    arq_redis_url: str                   # Redis URL for ARQ
    upstash_redis_rest_url: str          # Upstash REST URL
    upstash_redis_rest_token: str        # Upstash REST token
    anthropic_api_key: str = ""          # Not needed for scaffold
    notion_api_key: str = ""             # Not needed for scaffold
    notion_db_id: str = ""               # Not needed for scaffold
    worker_secret: str = ""              # Not needed for scaffold

    model_config = SettingsConfigDict(env_file=".env")
```

Required vars (`database_url`, `arq_redis_url`, `upstash_redis_rest_url`,
`upstash_redis_rest_token`) validated on startup — fails fast with clear messages.
Optional vars default to empty string so the scaffold runs without full config.

### Database (`app/database.py`)

- `create_async_engine` with `asyncpg` driver
- `async_sessionmaker` for request-scoped sessions
- Connection pool: 5 min, 20 max

### ARQ Worker (`jobs/worker.py`)

- `WorkerSettings` class with Redis connection from config
- One example `ping` job that logs a message and returns
- Future feature branches add their cron functions and jobs here

### Entrypoint (`entrypoint.sh`)

Runs both processes in the same container:
```bash
uvicorn worker.app.main:app --host 0.0.0.0 --port ${PORT:-8000} &
python -m arq worker.jobs.worker.WorkerSettings &
wait -n  # Exit if either process dies (bash 4.3+)
```

### Redis Client Clarification

- **ARQ**: Uses its own `arq.connections.RedisSettings` (standard Redis protocol) →
  connects to Upstash via `ARQ_REDIS_URL`
- **Upstash REST API**: Uses `httpx` for HTTP-based Redis access from Vercel-layer
  code. The `redis` package is not needed — removed from runtime deps.
- **Health check**: Uses `arq.connections.create_pool` to verify Redis connectivity

## Docker

### Dockerfile

Multi-stage build:
1. **Builder stage**: Python 3.12-slim, install deps from pyproject.toml via pip
2. **Runtime stage**: Python 3.12-slim, copy installed packages + source
3. Railway auto-detects `PORT` env var

### docker-compose.yml

Single `worker` service:
- Builds from `./worker`
- `env_file: .env`
- Exposes port 8000 for local FastAPI access

## Testing

- `pytest` + `pytest-asyncio` in dev deps
- `worker/app/test_main.py`: tests `/health` endpoint with mocked DB/Redis
- `worker/app/models/test_models.py`: validates model instantiation, enum values, timestamp mixin
- `worker/jobs/test_worker.py`: tests example ping job runs
- `worker/conftest.py`: shared async fixtures
- `pyproject.toml` configures `testpaths = ["app", "jobs"]` for pytest discovery
- No integration tests (deferred to Task 20, Wave 5; will add `testcontainers` as dev dep then)

## Dependencies (`pyproject.toml`)

### Runtime
- `fastapi`
- `uvicorn[standard]`
- `sqlalchemy[asyncio]`
- `asyncpg`
- `alembic`
- `arq`
- `pydantic-settings`
- `httpx`

### Dev
- `pytest`
- `pytest-asyncio`
- `ruff` (linting)

## Deliverables Checklist

- [ ] All files in directory structure above
- [ ] Alembic migration with all 7 tables
- [ ] Decision docs: `003-sqlalchemy-orm.md`, `004-no-local-dev-containers.md`
- [ ] Update `.env.example` with any new env vars (none expected beyond existing)
- [ ] Update `CHANGELOG.md` `[Unreleased]` section
- [ ] All tests passing

## What This Does NOT Include

- Actual poller implementations (feature/discovery)
- Scoring logic (feature/scoring)
- Content generation (feature/content-gen)
- Notion integration (feature/notion-staging)
- Next.js approval UI (feature/approval-ui)
- Integration tests (Task 20)
- CI/CD pipeline (separate chore branch)
