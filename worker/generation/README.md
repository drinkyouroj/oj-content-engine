# Content Generation Engine

## Purpose
Converts triaged topics into platform-specific content drafts (Substack, Twitter, LinkedIn, Instagram).
Implements PRD Sections 4 and 5.

## Structure
- `engine.py` — Orchestrator: topic → 4 platform drafts
- `llm_client.py` — Provider abstraction (Groq + Anthropic)
- `verticals.py` — Topic vertical detection
- `exemplar_selector.py` — Voice exemplar selection by vertical
- `voice_drift.py` — Substack second-pass critique
- `prompts/` — Platform-specific prompt templates

## How it fits in the pipeline
Input: Topic rows (status=queued) from triage engine.
Output: ContentDraft rows in Postgres, staged in Notion.

## Environment variables
- `GROQ_API_KEY` — Default LLM provider
- `ANTHROPIC_API_KEY` — Upgrade provider (optional)
- `GENERATION_MODEL_<PLATFORM>` — Per-platform model override (e.g., `anthropic/claude-sonnet-4-5`)
