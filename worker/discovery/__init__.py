"""
Trend discovery layer — pollers for RSS, Reddit, HN, and Twitter/X.

Implements PRD Section 2 (Trend Discovery Layer). Each poller inherits from
BasePoller and produces RawSignal instances that are deduplicated and persisted
to the signals table in Postgres.

Submodules:
    base        — BasePoller ABC and RawSignal dataclass
    dedup       — URL normalization, SHA-256 hashing, Levenshtein title matching
    rss_poller  — RSS/Atom feed poller via feedparser
    reddit_poller — Reddit JSON API poller
    hn_poller   — Hacker News Algolia API poller
    twitter_poller — Twitter/X API v2 poller (stub)
    alerts      — Dead source detection and system alert management
"""

from __future__ import annotations
