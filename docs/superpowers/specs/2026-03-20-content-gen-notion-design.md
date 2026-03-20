# Content Generation + Notion Staging Design

**Goal:** Convert triaged topics into platform-specific content drafts using LLM generation with brand voice injection, then stage drafts in Notion for Justin's review.

**Scope:** PRD Tasks 11-14 (content generation prompt architecture, voice-drift critique, per-platform branches, Notion staging). Worker layer only — no Vercel/Next.js changes.

**Depends on:** Waves 1-3 complete (infrastructure, discovery, scoring, triage).

---

## 0. PRD Deviations

This spec intentionally deviates from the PRD in two areas:

1. **Default LLM provider: Groq instead of Claude Sonnet.** The PRD specifies Claude Sonnet for all generation (Section 4, Section 8), noting "Quality bottleneck — Haiku insufficient for voice work." This spec defaults to Groq/Llama 3.3 70B for cost and speed, with Anthropic as a per-platform upgrade path. Rationale: start cheap, use the quality comparison test harness to evaluate voice quality empirically, and selectively upgrade platforms where Groq falls short. A decision doc (`docs/decisions/004-groq-default-generation.md`) will be written alongside implementation.

2. **Context injection simplification: vertical-matched exemplars instead of Notion article retrieval.** The PRD says context injection includes "3 similar past Notion articles (by title similarity)." This spec replaces that with vertical-aware voice exemplar selection. Rationale: at launch the Notion database is empty, so there are no past articles to retrieve. The exemplar system provides the same voice-anchoring function. Notion article retrieval can be added later as the corpus grows.

---

## 1. Content Generation Architecture

### Three-Layer Prompt System

Each generation call assembles a prompt from three layers:

1. **System prompt** — Brand voice bible (verbatim from PRD brand spec), platform-specific constraints, hard-no list as negative examples. Static per platform, versioned in code.

2. **Context injection** — Topic signal data (title, body preview, source, source metrics), score breakdown (all 6 dimensions), and 3-5 voice exemplars selected by vertical similarity. Exemplars are tagged with a `vertical` field and matched to the topic's detected vertical.

3. **Generation prompt** — Platform-specific instructions (length, structure, tone) plus Justin's thesis if provided. Thesis-less drafts include a metadata flag: `"AI-originated — heavy edit needed"`.

### Configurable LLM Provider

Models are configurable per platform:

```python
GENERATION_MODELS = {
    "substack": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    "twitter": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    "linkedin": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    "instagram": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    "substack_critique": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
}
```

Supported providers: `groq` (default, fast/cheap) and `anthropic` (upgrade path for voice quality). A `LLMClient` abstraction wraps both providers so prompt code is provider-agnostic. Provider and model are overridable via environment variables. The `substack_critique` key allows the voice-drift critique pass to use a different (potentially higher-quality) model than the initial Substack generation.

### Voice-Drift Self-Critique (Substack Only)

Substack long-form gets a dedicated second LLM pass after initial generation:

- Input: the generated Substack draft
- Prompt: "You are a drinkYourOJ subscriber who has read every post since 2023. Read this draft. Flag every sentence that sounds like it could appear in a generic tech newsletter, a press release, or a crypto hype blog. For each flagged sentence, explain why it's off-brand and rewrite it in Justin's voice: dry, direct, systems-thinking, occasionally funny, never breathless."
- Output: revised draft replaces the original

Twitter, LinkedIn, and Instagram are single-pass only. Short formats don't have room to drift.

### Per-Platform Output Specs

| Platform | Length | Structure | Special |
|----------|--------|-----------|---------|
| Substack | 1,500-2,500 words | Hook → analysis → contrarian conclusion | Two-pass (draft + voice-drift critique) |
| Twitter | 5-12 tweets, each <= 280 chars | Hook tweet → substance → CTA | Thread format, character count enforced |
| LinkedIn | 300-600 words | Opening hook → 3 insight paragraphs → closing | Professional but honest tone |
| Instagram | 150-word caption + image card prompt | Visual concept + concise caption | Image card prompt stored as text, no actual image generation |

### Quality Comparison Tests

A test harness generates the same topic through both Groq and Anthropic providers, saves outputs side-by-side to files, and prints a comparison summary. This is a manual review tool, not an automated quality gate — human judgment determines which model produces better voice fidelity.

---

## 2. Voice Exemplar System

### Seeding

A scraper script fetches full article text from 7 Substack URLs:

- `schneider-solved-the-salary-cap-while-everyone-else-complained`
- `13-3-the-box-score-that-ended-the-can-seattles-defense-travel-debate`
- `disguise-and-destroy-the-macdonald-method-that-broke-nfl-offenses`
- `trump-is-covering-up-the-minneapolis-ice-shooting-just-like-hes-covering-up-epstein`
- `nodes-over-numbers`
- `the-false-balance-trap`
- `my-autism-self-assessment-scores`

Each is stored in the `voice_exemplars` table with `platform=substack` and an auto-detected `vertical`.

### Vertical Taxonomy

Exemplars and topics are tagged with one of:

| Vertical | Description | Exemplar examples |
|----------|-------------|-------------------|
| `ai_politics` | AI regulation, tech policy, governance | (future exemplars) |
| `depin` | Decentralized infrastructure, blockchain | "Nodes Over Numbers" |
| `sports_seahawks` | NFL/Seahawks analysis | "Schneider Solved the Salary Cap", "13-3", "Disguise and Destroy" |
| `media` | Media criticism, journalism, narrative analysis | "The False Balance Trap" |
| `personal` | Personal essays, neurodivergence, identity | "My Autism Self-Assessment Scores" |

Vertical detection uses keyword matching against the topic title and body — same lightweight approach as the scoring rubric's resonance taxonomy. Not LLM-powered.

### Schema Changes

Two Alembic migrations:

**Migration 002: `002_add_exemplar_vertical.py`**
```sql
ALTER TABLE voice_exemplars ADD COLUMN vertical VARCHAR(50) DEFAULT 'general';
```

**Migration 003: `003_add_draft_metadata_and_topic_vertical.py`**
```sql
ALTER TABLE content_drafts ADD COLUMN generation_metadata JSONB DEFAULT '{}';
ALTER TABLE topics ADD COLUMN vertical VARCHAR(50);
```

The `generation_metadata` JSONB column on `content_drafts` stores generation flags:
- `"no_exemplars_available": true` — when no voice exemplars matched
- `"ai_originated": true` — when no thesis was provided
- `"voice_drift_applied": true` — when Substack critique pass ran
- `"prompt_version": "..."` — hash of the prompt template used

The `vertical` column on `topics` persists the detected vertical for auditability and debugging of exemplar selection.

### Exemplar Selection Logic

For each generation run:
1. Query `voice_exemplars` where `platform` matches target platform AND `active = true`
2. Filter to exemplars whose `vertical` matches the topic's detected vertical
3. If >= 3 matches, randomly select 3-5
4. If < 3 matches, fill remaining slots from other verticals (random)
5. If zero exemplars exist, proceed without voice examples and flag `"no_exemplars_available": true` in draft metadata

### Graceful Degradation

Generation never crashes due to missing exemplars. Zero exemplars means the system prompt and thesis carry the voice load alone. The draft metadata flags this so Justin knows the output had no voice examples.

---

## 3. Notion Staging

### Integration Pattern

Worker writes drafts to the Second Brain database (`b6ef1af3-2b70-4346-a107-e4b21a754b3e`) after generation completes. One Notion page per content draft — a topic with 4 platform drafts creates 4 Notion pages.

### Page Properties

| Property | Type | Source |
|----------|------|--------|
| Title | Title | `[Platform] Topic Title` (e.g., `[Substack] The AI Safety Theater Problem`) |
| Platform | Select | substack / twitter / linkedin / instagram |
| Status | Select | Draft (initial value) |
| Composite Score | Number | From `scored_signal.composite_score` |
| Score Breakdown | Rich Text | Formatted per-dimension scores |
| Generated At | Date | Timestamp of generation |
| Topic ID | Text | UUID linking back to Postgres `topics` table |
| Thesis Provided | Checkbox | From `topic.thesis_provided` |
| Model Used | Text | e.g., `groq/llama-3.3-70b-versatile` |
| Token Cost | Number | Approximate USD |

### Page Body

The draft content, formatted for the target platform:
- Substack: full article with markdown heading hierarchy
- Twitter: numbered tweets with character counts
- LinkedIn: formatted post
- Instagram: caption text + image card prompt (separated by a divider)

### Page Comments

Generation metadata as a comment on the page: model version, prompt version hash, generation timestamp, token usage breakdown.

### Rate Limiting

Notion API caps at 3 requests/second. The staging job batches writes with 400ms delays between API calls. Each Notion page creation is a separate API call (create page + add comment = 2 calls per draft).

### Bidirectional Linking

The `notion_page_id` returned from the Notion API is stored on the `ContentDraft` row in Postgres. This enables the future approval UI to link directly to Notion pages for editing.

### Error Handling

- ContentDraft is always saved to Postgres first (source of truth)
- If Notion write fails, `notion_page_id` stays null and a `system_alert` is created:
  - `alert_type = "notion_write_failed"`, `source = "notion"`, `message` = error details
  - These are single-occurrence alerts (not using `consecutive_failures` — that pattern is for poller health)
- If LLM generation fails for a platform, a `system_alert` is created:
  - `alert_type = "generation_failed"`, `source = "generation"`, `message` = platform + error
- A manual retry can be triggered via the ARQ job
- Notion downtime does not block generation — drafts are still reviewable in Postgres

---

## 4. File Structure

### New Files

```
worker/
├── generation/
│   ├── __init__.py
│   ├── llm_client.py              # Provider abstraction (Groq + Anthropic)
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── system.py              # Brand voice bible, hard-no list
│   │   ├── substack.py            # Substack generation prompt
│   │   ├── twitter.py             # Twitter thread prompt
│   │   ├── linkedin.py            # LinkedIn post prompt
│   │   └── instagram.py           # Instagram caption + card prompt
│   ├── voice_drift.py             # Substack second-pass critique
│   ├── exemplar_selector.py       # Vertical-aware exemplar selection
│   ├── engine.py                  # Orchestrator: topic → 4 platform drafts
│   ├── test_llm_client.py
│   ├── test_engine.py
│   ├── test_voice_drift.py
│   └── test_exemplar_selector.py
├── notion/
│   ├── __init__.py
│   ├── client.py                  # Notion API wrapper (rate-limited)
│   ├── staging.py                 # Draft → Notion page creation
│   ├── test_client.py
│   └── test_staging.py
├── jobs/
│   ├── generation_jobs.py         # ARQ job: generate drafts for a topic
│   └── notion_jobs.py             # ARQ job: stage drafts in Notion
├── scripts/
│   ├── seed_exemplars.py          # One-time: scrape Substack URLs → voice_exemplars
│   └── compare_models.py          # Quality comparison: same topic through Groq vs Anthropic
```

### Modified Files

- `worker/jobs/worker.py` — Register `run_generation_job` and `run_notion_staging_job` in `WorkerSettings.functions`
- `worker/scoring/rubric.py` — Expand `RESONANCE_TAXONOMY` with sports_seahawks, media, personal verticals
- `worker/pyproject.toml` — Add `generation`, `notion`, `scripts` to testpaths; add `notion-client`, `beautifulsoup4` dependencies
- `worker/alembic/versions/002_add_exemplar_vertical.py` — Migration for `vertical` column on voice_exemplars
- `worker/alembic/versions/003_add_draft_metadata_and_topic_vertical.py` — Migration for `generation_metadata` JSONB on content_drafts, `vertical` on topics
- `worker/conftest.py` — Add dummy env vars for `NOTION_API_KEY`, `NOTION_DB_ID`

---

## 5. Data Flow

```
Topic (status=queued or review+approved, thesis optional)
  ↓
Generation engine (single ARQ job per topic, sequential per platform):
  1. Detect topic vertical from title/body keywords → store on Topic.vertical
  2. Select 3-5 voice exemplars by vertical match
  3. For each platform (substack, twitter, linkedin, instagram):
     a. Assemble 3-layer prompt (system + context + generation)
     b. Call LLM (provider per platform config)
     c. Substack only: run voice-drift critique (2nd LLM call)
     d. Save ContentDraft row to Postgres with generation_metadata
     e. On LLM failure: log error, skip this platform, continue to next
  4. Update Topic.status → "generated" (even if some platforms failed)
  ↓
Notion staging job (fires after generation):
  1. Query ContentDrafts where notion_page_id is null
  2. For each draft:
     a. Create Notion page with properties + body
     b. Add metadata comment
     c. Store notion_page_id back on ContentDraft
     d. 400ms delay between API calls (between every API call, including create-to-comment)
  3. On Notion write failure: create system_alert(alert_type="notion_write_failed")
```

**Platform isolation:** The PRD specifies each platform as an independent ARQ task. This spec uses a single ARQ job that loops sequentially, with per-platform error isolation: if Twitter generation fails, LinkedIn and Instagram still proceed. This is simpler than 4 separate ARQ tasks and achieves the same partial-success guarantee. The `generation_metadata` on each ContentDraft records whether generation succeeded or was skipped.

### ARQ Job Registration

```python
# worker/jobs/worker.py
functions = [
    ping, poll_rss, poll_reddit, poll_hn, poll_twitter,
    run_scoring_pipeline, run_triage_job,
    run_generation_job,      # NEW
    run_notion_staging_job,   # NEW
]
```

Generation can be triggered by cron (process all queued topics periodically) or manually. Notion staging fires automatically after generation completes (called at the end of the generation job).

---

## 6. Rubric Expansion

The scoring rubric's `RESONANCE_TAXONOMY` expands to surface content across all verticals:

```python
RESONANCE_TAXONOMY = {
    "core": {
        "keywords": [
            # Existing AI/politics keywords...
            "artificial intelligence", "ai regulation", "ai safety", ...
        ]
    },
    "direct": {
        "keywords": [
            # Existing direct keywords...
            "openai", "anthropic", "deepseek", ...
            # NEW: Seahawks/NFL
            "seahawks", "seattle seahawks", "nfl", "mike macdonald",
            "geno smith", "jaxon smith-njigba", "nfc west",
            # NEW: Media
            "media criticism", "false balance", "journalism ethics",
        ]
    },
    "adjacent": {
        "keywords": [
            # Existing adjacent keywords...
            "decentralized compute", "cloud computing", ...
            # NEW: Broader sports/media
            "salary cap", "nfl draft", "football analytics",
            "content moderation", "narrative framing",
            "neurodivergence", "autism", "indie creator",
        ]
    },
}
```

This ensures the discovery and scoring pipeline surfaces content from all of Justin's verticals, not just AI/politics.

---

## 7. Dependencies

### Python Packages (new)

| Package | Version | Purpose |
|---------|---------|---------|
| `notion-client>=2.2.0` | Official Notion SDK for Python (uses httpx internally) |
| `beautifulsoup4>=4.12.0` | Parse Substack HTML for exemplar seeding (httpx already in deps for fetching) |

### Environment Variables (new or newly required)

| Variable | Purpose | Required |
|----------|---------|----------|
| `NOTION_API_KEY` | Notion integration token | Yes (for Notion staging) |
| `NOTION_DB_ID` | Second Brain database ID | Yes (for Notion staging) |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | Only if using Anthropic provider |
| `GROQ_API_KEY` | Groq API key | Yes (default provider) |
| `GENERATION_MODEL_SUBSTACK` | Override model for Substack | No (defaults to config dict) |
| `GENERATION_MODEL_TWITTER` | Override model for Twitter | No |
| `GENERATION_MODEL_LINKEDIN` | Override model for LinkedIn | No |
| `GENERATION_MODEL_INSTAGRAM` | Override model for Instagram | No |

---

## 8. Testing Strategy

| Module | Test Approach | Framework |
|--------|--------------|-----------|
| `llm_client.py` | Mock provider APIs, verify prompt assembly and response parsing | pytest + respx |
| `engine.py` | Mock LLM client, verify orchestration flow, draft creation, status updates | pytest |
| `voice_drift.py` | Mock LLM client, verify critique prompt structure and draft replacement | pytest |
| `exemplar_selector.py` | Unit tests with in-memory exemplars, verify vertical matching and fallback | pytest |
| `prompts/*.py` | Snapshot tests — assert prompt structure and variable injection, not exact text | pytest |
| `notion/client.py` | Mock Notion API, verify rate limiting and error handling | pytest + respx |
| `notion/staging.py` | Mock Notion client, verify page property mapping and bidirectional ID storage | pytest |
| Quality comparison | Generate same topic via Groq and Anthropic, save side-by-side for human review | pytest (manual) |

All test files live alongside source files. Tests use mocked HTTP responses — no real LLM or Notion calls in CI.
