# Deploy Worker (Railway)

## Overview

The Worker layer (FastAPI + ARQ) deploys to Railway. It auto-deploys on push to `develop`.

- **Railway URL**: https://worker-production-5c9f.up.railway.app
- **GitHub repo**: `drinkyouroj/oj-content-engine`
- **Branch**: `develop`
- **Root directory**: `worker`
- **Builder**: Dockerfile

## Processes

Two processes run via `entrypoint.sh`:

1. **uvicorn** — FastAPI HTTP server
2. **arq** — Background/cron job worker

## Health Check

```bash
curl https://worker-production-5c9f.up.railway.app/health
# {"status":"healthy","database":true,"redis":true}
```

## Environment Variables

Set via Railway dashboard or CLI:

```bash
railway variable set KEY=VALUE --service worker
```

Required variables: `DATABASE_URL`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `ANTHROPIC_API_KEY`, `NOTION_API_KEY`, `NOTION_DB_ID`, `WORKER_SECRET`, `RSS_FEED_URLS`.

## Logs

```bash
railway logs --service worker --lines 200
```

Logs are structured JSON.

## Deploy Workflow

1. Push to `develop` (or merge a PR into `develop`).
2. Railway detects the push, builds the Docker image from `worker/Dockerfile`.
3. Railway runs `entrypoint.sh`, starting both uvicorn and arq.
4. Health check confirms DB + Redis connectivity.

## Manual Redeploy

Trigger a redeploy from the Railway dashboard if needed, or push an empty commit:

```bash
git commit --allow-empty -m "chore(ci): trigger redeploy"
git push origin develop
```
