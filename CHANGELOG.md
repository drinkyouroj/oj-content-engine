# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project initialization: CLAUDE.md, PRD, docs structure, decision log
- Architecture documentation (docs/architecture.md)
- Decision 001: Vercel + Worker two-host split
- Decision 002: Upstash Redis over self-hosted Redis
- Environment variable template (.env.example)
- Worker layer scaffold: FastAPI + ARQ + Docker (Railway)
- Postgres schema: 7 tables (signals, scored_signals, topics, content_drafts, voice_exemplars, scoring_adjustments, system_alerts)
- Alembic async migration framework with initial migration
- Health endpoint (/health) with DB and Redis connectivity checks
- Decision docs: 003 (SQLAlchemy ORM), 004 (no local dev containers)
- Content generation engine with 3-layer prompt architecture (system + context + generation)
- Per-platform prompt templates (Substack, Twitter, LinkedIn, Instagram)
- Voice-drift self-critique for Substack long-form (second LLM pass)
- Configurable LLM provider per platform (Groq default, Anthropic upgrade path)
- Vertical-aware voice exemplar selection (sports_seahawks, ai_politics, depin, media, personal)
- Notion staging with rate-limited API client and bidirectional linking
- Exemplar seeding script for Substack articles
- Model quality comparison script (Groq vs Anthropic)
- Rubric expansion: sports/Seahawks, media, personal keywords
- Approval UI: Next.js dashboard with topic review and content approval workflow
- Token-based authentication via middleware
- Dashboard overview with stats cards and topic list
- Topic review page with score breakdown, thesis input, platform draft previews
- API routes: approve, reject, thesis, topic-action, regenerate, health
- Notion status sync on approve/reject (best-effort)
- Worker regeneration endpoint (POST /api/regenerate/{topic_id})

### Changed
- Expanded RESONANCE_TAXONOMY with multi-vertical keywords
- Added `vertical` column to voice_exemplars and topics tables
- Added `generation_metadata` JSONB column to content_drafts table
