# Deploy Vercel (Next.js)

## Overview

The Next.js approval UI deploys to Vercel. It auto-deploys from GitHub.

- **Project**: `oj-content-engine`
- **URL**: https://oj-content-engine.vercel.app
- **Linked via**: `.vercel/` directory in repo root

## Deploy Commands

Auto-deploy from GitHub (preferred):

```bash
git push origin develop
```

Manual production deploy:

```bash
vercel --prod
```

## Environment Variables

Set via Vercel dashboard or CLI:

```bash
vercel env add NAME production
```

Required variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Neon Postgres connection string |
| `WORKER_URL` | Railway Worker URL |
| `WORKER_SECRET` | Shared secret for Worker API auth |
| `DASHBOARD_TOKEN` | Token for dashboard access |
| `NOTION_API_KEY` | Notion integration token |
| `NOTION_DB_ID` | Notion Second Brain database ID |
| `UPSTASH_REDIS_REST_URL` | Upstash Redis REST endpoint |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash Redis auth token |

## Authentication

Token-based auth via `middleware.ts`. Access the dashboard by appending the token as a query parameter:

```
https://oj-content-engine.vercel.app/dashboard?token=<DASHBOARD_TOKEN>
```

Or pass the `x-dashboard-token` header in API requests.

## Verifying Deployment

Check the Worker health proxy:

```bash
curl -H "x-dashboard-token: <TOKEN>" https://oj-content-engine.vercel.app/api/health
```
