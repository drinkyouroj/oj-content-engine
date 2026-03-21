# Worker Layer

## Purpose

The Worker layer runs long-running pipeline operations: trend discovery,
signal scoring, content generation, and Notion staging. Built with
FastAPI + ARQ on Docker, deployed to Railway. Implements PRD Sections 1-5.

## Structure

- `app/` — FastAPI application, config, database, ORM models
- `jobs/` — ARQ worker configuration and background job definitions
- `alembic/` — Database migration files

## How it fits in the pipeline

The Worker is the data processing engine. It polls external sources,
scores signals, generates content, and writes to Notion. It shares
Neon Postgres and Upstash Redis with the Vercel layer.

## Environment variables required

See `.env.example` in the project root. Required for Worker:
- `DATABASE_URL` — Neon Postgres connection string
- `ARQ_REDIS_URL` — Redis URL for ARQ task queue
- `UPSTASH_REDIS_REST_URL` — Upstash REST URL
- `UPSTASH_REDIS_REST_TOKEN` — Upstash REST token

## Running locally

```bash
# Install dependencies
cd worker && pip install -e ".[dev]"

# Run FastAPI dev server
uvicorn worker.app.main:app --reload --port 8000

# Run ARQ worker (separate terminal)
arq worker.jobs.worker.WorkerSettings

# Run tests
pytest

# Run with Docker
docker compose up --build
```
