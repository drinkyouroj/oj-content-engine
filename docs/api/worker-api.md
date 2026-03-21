# Worker API Reference

Base URL: `http://localhost:8001` (local) / `https://worker-production-5c9f.up.railway.app` (production)

All endpoints except `/health` require the `x-worker-secret` header matching the `WORKER_SECRET` env var.

---

## GET /health

Health check. Verifies database and Redis connectivity.

**Auth**: None

**Response** `200`:
```json
{
  "status": "healthy",
  "database": true,
  "redis": true
}
```

---

## POST /api/regenerate/{topic_id}

Re-queue a topic for Substack draft generation.

**Auth**: `x-worker-secret` header

**Path params**:
- `topic_id` (UUID) — The topic to regenerate

**Response** `200`:
```json
{
  "status": "queued",
  "topic_id": "uuid"
}
```

**Errors**: `401` unauthorized, `404` topic not found

---

## POST /api/suggest-theses/{topic_id}

Generate 3-5 thesis suggestions for a topic using Claude Haiku.

**Auth**: `x-worker-secret` header

**Path params**:
- `topic_id` (UUID)

**Response** `200`:
```json
{
  "theses": [
    "Thesis suggestion 1",
    "Thesis suggestion 2",
    "Thesis suggestion 3"
  ]
}
```

**Errors**: `401` unauthorized, `404` topic not found

---

## POST /api/generate-social/{topic_id}/{platform}

Generate social content for a topic from its existing Substack draft.

**Auth**: `x-worker-secret` header

**Path params**:
- `topic_id` (UUID)
- `platform` — One of: `twitter`, `linkedin`, `instagram`

**Response** `200`:
```json
{
  "status": "generated",
  "platform": "twitter",
  "draft_id": "uuid"
}
```

**Errors**: `401` unauthorized, `404` topic not found, `400` invalid platform or missing Substack draft

---

## POST /api/research

Search the signals database and Brave Search for research material.

**Auth**: `x-worker-secret` header

**Request body**:
```json
{
  "query": "search terms"
}
```

**Response** `200`:
```json
{
  "signals": [...],
  "web_results": [...]
}
```

**Errors**: `401` unauthorized

---

## POST /api/create-topic

Create a synthesized topic from multiple selected articles/signals.

**Auth**: `x-worker-secret` header

**Request body**:
```json
{
  "articles": [
    {
      "title": "Article title",
      "url": "https://...",
      "summary": "Brief summary"
    }
  ]
}
```

**Response** `200`:
```json
{
  "status": "created",
  "topic_id": "uuid"
}
```

**Errors**: `401` unauthorized, `400` invalid articles payload
