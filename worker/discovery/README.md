# discovery

## Purpose

Trend discovery layer for the OJ Content Engine. Polls external sources (RSS feeds,
Reddit, Hacker News, Twitter/X) for signals relevant to the drinkYourOJ brand topics
(DePIN, decentralized infrastructure, AI tooling, blockchain infrastructure). Discovered
signals are deduplicated and persisted to the `signals` table for downstream scoring
and triage.

Implements PRD Section 2 (Trend Discovery Layer).

## Structure

| File | Description |
|---|---|
| `__init__.py` | Package docstring |
| `base.py` | `BasePoller` abstract class and `RawSignal` dataclass |
| `dedup.py` | URL normalization, SHA-256 hashing, Levenshtein title similarity |
| `rss_poller.py` | RSS/Atom feed poller via feedparser |
| `reddit_poller.py` | Reddit JSON API poller (public, no auth) |
| `hn_poller.py` | Hacker News Algolia API poller |
| `twitter_poller.py` | Twitter/X API v2 poller (stub — requires paid bearer token) |
| `alerts.py` | Dead source detection — tracks consecutive zero-result runs |
| `test_dedup.py` | Unit tests for dedup utilities |
| `test_rss_poller.py` | Unit tests for RSS poller (mocked feedparser) |
| `test_reddit_poller.py` | Unit tests for Reddit poller (mocked httpx via respx) |
| `test_hn_poller.py` | Unit tests for HN poller (mocked httpx via respx) |
| `test_alerts.py` | Unit tests for alert creation/update/resolution |

## How it fits in the pipeline

```
External Sources (RSS, Reddit, HN, Twitter)
    │
    ▼
Discovery Pollers (this module)
    │  fetch() → RawSignal list
    │  dedup via SHA-256 hash + Levenshtein title similarity
    │  persist to signals table
    │  update dead source alerts
    ▼
Signals Table (Postgres)
    │
    ▼
Scoring & Triage Layer (worker/scoring — future)
```

Data flows in one direction: external sources → pollers → signals table. Each poller
is triggered by an ARQ cron job defined in `worker/jobs/discovery_jobs.py`.

## Environment variables required

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Postgres connection string for signal persistence |
| `RSS_FEED_URLS` | No | Comma-separated list of RSS feed URLs to poll |
| `TWITTER_BEARER_TOKEN` | No | Twitter API v2 bearer token (stub — poller disabled without it) |

Reddit and HN pollers use public APIs and do not require authentication.

## Running locally

```bash
# Install dependencies (from worker/ directory)
pip install -e ".[dev]"

# Run all discovery tests
python3.12 -m pytest discovery/ -v

# Run a specific test file
python3.12 -m pytest discovery/test_dedup.py -v
```

## Cron schedules

| Job | Schedule | Rationale |
|---|---|---|
| `poll_rss` | Every 4 hours | RSS feeds update infrequently |
| `poll_reddit` | Every 1 hour | Hot posts rotate frequently |
| `poll_hn` | Every 1 hour | Front page rotates frequently |
| `poll_twitter` | Every 2 hours | Rate limits on Twitter API |
