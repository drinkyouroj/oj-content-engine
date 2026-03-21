# Local Dev Setup

## Prerequisites

- **Python 3.12** — Worker layer
- **Node.js 22** — Next.js Vercel layer
- **Postgres** — Neon (remote, connection string in env)
- **Redis** — Upstash (remote, REST URL in env)

## Environment

Copy the example env file and fill in all values:

```bash
cp .env.example .env.local
```

The Worker reads from `../.env.local` (project root) or its own `.env.local`. The Next.js app reads from the root `.env.local` as usual.

Key local overrides:

```bash
WORKER_URL=http://localhost:8001
```

## Database Migrations

Run Alembic migrations before first startup:

```bash
cd worker && python -m alembic upgrade head
```

## Running the Stack

Three terminals are required:

### Terminal 1 — ARQ Worker (cron jobs + background tasks)

```bash
cd worker && python3.12 -m arq worker.jobs.worker.WorkerSettings
```

### Terminal 2 — Worker FastAPI (API on port 8001)

```bash
cd worker && python3.12 -m uvicorn worker.app.main:app --port 8001
```

### Terminal 3 — Next.js (UI on port 3000)

```bash
npm run dev
```

## Accessing the Dashboard

Open in browser:

```
http://localhost:3000/dashboard?token=<DASHBOARD_TOKEN>
```

Where `<DASHBOARD_TOKEN>` matches the value in your `.env.local`.

## Verifying Health

Check the Worker health endpoint:

```bash
curl http://localhost:8001/health
# {"status":"healthy","database":true,"redis":true}
```
