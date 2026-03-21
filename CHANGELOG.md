# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] — 2026-03-20

### Added
- Full end-to-end content pipeline: discover → score → triage → thesis → generate → stage → approve
- Trend discovery: RSS, Reddit (via RSS feeds), Hacker News, Twitter/X pollers
- Two-pass signal scoring: Pass 1 rule-based, Pass 2 LLM-assisted (Claude Haiku)
- Triage engine with hard gates and composite score thresholds
- Content generation: Substack (Sonnet + voice-drift critique), social on-demand (Haiku 4.5)
- Substack-first generation flow: Substack generates automatically, social content (Twitter, LinkedIn, Instagram) generated on-demand from the Substack article
- Voice exemplar system with vertical-aware selection
- Notion staging with rate-limited API client and bidirectional status sync
- Approval UI: Next.js dashboard with topic review, score breakdown, thesis input, draft previews
- Steered topic research: `/dashboard/research` page with Brave Search + DB signal search, synthesized multi-source topics
- Thesis suggestion system (Claude Haiku generates 3-5 thesis candidates)
- Auto-refresh on the review page while content is generating
- Structured JSON logging across all pipeline stages with timing and context
- Token-based authentication via middleware
- Cloud deployment: Vercel (Next.js) + Railway (Worker with Docker)
- GitHub Actions CI: TypeScript check + Next.js build + ruff lint + pytest
- Runbooks: local dev setup, deploy worker, deploy vercel, add new platform
- API reference documentation for Worker endpoints and Notion schema
- 5 architecture decision records
- 244 Python tests across all pipeline stages

### Changed
- Reddit poller switched from blocked JSON API to public RSS feeds
- Social content models changed from Groq (llama-3.3-70b) to Anthropic Claude Haiku 4.5
- Source citations in Substack prompts now restricted to provided URLs only (no more SOURCE NEEDED placeholders)
- Database: added `signal_id` direct FK on topics, `scored_signal_id` made nullable for steered topics
- All DB queries use LEFT JOIN + COALESCE for nullable scored_signal support
