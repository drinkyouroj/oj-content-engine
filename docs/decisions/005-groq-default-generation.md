# 005 — Groq as Default Generation Provider
_Date: 2026-03-20 | Status: Accepted_

## Context
The PRD specifies Claude Sonnet for all content generation, noting voice quality
as a bottleneck. However, Groq offers fast, cheap inference with llama-3.3-70b
which may be sufficient for initial testing.

## Options Considered
1. Claude Sonnet for all platforms — highest quality, ~$0.08/topic
2. Groq for all platforms — fast and cheap, quality unknown
3. Hybrid: Anthropic for Substack, Groq for short-form — best of both

## Decision
Default to Groq for all platforms with per-platform override via environment
variables (GENERATION_MODEL_<PLATFORM>=provider/model). Use the comparison
script to evaluate voice quality empirically before upgrading.

## Consequences
- Lower cost during development and testing
- Easy upgrade path per platform when quality issues surface
- Risk: voice quality may be insufficient for Substack long-form
- Mitigation: compare_models.py script + voice-drift critique second pass
