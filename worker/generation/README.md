# Content Generation Engine

## Purpose
Converts triaged topics into platform-specific content drafts (Substack, Twitter, LinkedIn, Instagram).
Implements PRD Sections 4 and 5.

## Structure
- `engine.py` — Orchestrator: topic → 4 platform drafts
- `llm_client.py` — Provider abstraction (Anthropic primary; Groq for scoring Pass 2 if configured)
- `verticals.py` — Topic vertical detection
- `exemplar_selector.py` — Voice exemplar selection by vertical
- `voice_drift.py` — Substack second-pass critique
- `prompts/` — Platform-specific prompt templates

## How it fits in the pipeline
Input: Topic rows (status=queued) from triage engine.
Output: ContentDraft rows in Postgres, staged in Notion.

## Environment variables
- `ANTHROPIC_API_KEY` — Primary LLM provider (Substack uses Claude Sonnet, social content uses Claude Haiku 4.5)
- `GROQ_API_KEY` — Used for scoring Pass 2 if configured (optional)
- `GENERATION_MODEL_<PLATFORM>` — Per-platform model override (e.g., `anthropic/claude-sonnet-4-5`)

## Running locally

```bash
cd worker && python -m pytest generation/ -v
```
