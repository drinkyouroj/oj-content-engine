# CLAUDE.md — Content Pipeline
_Owner: Justin (drinkYourOJ) | Read this file before touching anything._

---

## Project Overview

An automated content creation pipeline for the drinkYourOJ brand. Discovers trends from RSS,
Twitter/X lists, and Reddit/HN; scores and triages them against a brand rubric; generates
platform-specific content (Substack, Twitter/X, LinkedIn, Instagram); stages drafts in Notion
for human approval; and publishes only after explicit sign-off.

**The PRD (`output/PRD.md`) is the source of truth for what gets built.** If this file and
the PRD conflict, the PRD wins. Update this file to match.

---

## Architecture: Two-Layer Split

This project runs on two distinct hosts. Every file, route, and job must belong to exactly
one layer. When in doubt, ask before assuming.

```
┌─────────────────────────────────────────────────┐
│  VERCEL LAYER  (Next.js App Router)             │
│  - Approval UI (review / approve / reject)      │
│  - /app/api/ route handlers (lightweight only)  │
│  - Vercel Postgres (Neon) — structured data     │
│  - Upstash Redis — queue visibility, pub/sub    │
│  - Vercel Blob / S3 — static assets             │
│  Hard limit: NO long-running ops (≤60s max)     │
└────────────────────┬────────────────────────────┘
                     │ shared Postgres + Redis
┌────────────────────▼────────────────────────────┐
│  WORKER LAYER  (FastAPI + ARQ, Docker)          │
│  - Trend discovery: RSS, Twitter/X, Reddit/HN   │
│  - Signal scoring and triage                    │
│  - LLM content generation (Claude API)          │
│  - Notion writes                                │
│  - Playwright Substack automation               │
│  Hosts: local Docker / Railway / Fly.io         │
└─────────────────────────────────────────────────┘
```

**Rule**: If a task involves an LLM call, external scraping, or could take more than 5 seconds,
it belongs in the Worker layer. No exceptions without a written justification in a DECISION doc.

---

## Git Flow — Mandatory, No Exceptions

### Branch Structure
```
main        ← production only. Never commit here directly.
develop     ← integration. All feature branches merge here via PR.
feature/*   ← all new work
fix/*       ← bug fixes
chore/*     ← deps, config, tooling
release/*   ← cut from develop when shipping. Merges to main + develop.
hotfix/*    ← emergency fixes cut from main. Merges to main + develop.
```

### Rules Claude Code Must Follow
1. **Never** run `git commit` to `main` or `develop` directly.
2. **Never** run `git merge` into `main` or `develop` directly.
3. Always create a feature branch before writing any code: `git checkout -b feature/<scope>`
4. Always push to the feature branch: `git push origin feature/<scope>`
5. When a feature is complete, say: _"Ready for PR: `feature/<scope>` → `develop`"_ and stop.
   Do not merge. Justin merges.
6. One branch per PRD implementation task (see PRD Section 11).
7. Branch names must match the PRD task scope exactly where possible.

### Release Flow
```bash
git checkout develop
git checkout -b release/0.1.0
# bump version in package.json / pyproject.toml
git commit -m "chore(release): bump to 0.1.0"
git push origin release/0.1.0
# Justin opens PR: release/0.1.0 → main
# Justin opens PR: release/0.1.0 → develop
# Justin tags: git tag -a v0.1.0 -m "v0.1.0"
```

### Semantic Versioning
Format: `MAJOR.MINOR.PATCH`

| Change type | Bump |
|---|---|
| New pipeline stage added | MINOR |
| Bug fix, prompt tweak, config change | PATCH |
| Breaking schema change, API contract change | MAJOR |
| New platform output (e.g. add TikTok) | MINOR |

Milestones are defined in PRD Section 9. Check there for v0.1.0 / v0.2.0 / v1.0.0 scope.

---

## Conventional Commits — Mandatory

Format: `<type>(<scope>): <subject>`

**Types**: `feat` `fix` `chore` `docs` `refactor` `test` `ci`

**Scopes** (use these exactly):
- `discovery` — trend ingestion layer
- `scoring` — signal scoring and ranking
- `triage` — rubric application
- `generation` — LLM content generation
- `notion` — Notion staging integration
- `approval-ui` — Next.js approval interface
- `worker` — ARQ jobs, FastAPI worker app
- `vercel` — Next.js app, API routes
- `db` — schema migrations, Postgres
- `redis` — queue config, Upstash
- `auth` — any auth-related work
- `ci` — GitHub Actions, deployment config
- `deps` — dependency updates

**Examples**:
```
feat(discovery): add Reddit HN poller with exponential backoff
fix(triage): correct brand score weighting for DePIN topics
chore(deps): pin anthropic-sdk to 0.25.x
docs(worker): add ARQ job lifecycle diagram to README
refactor(generation): extract prompt builder into dedicated module
test(scoring): add unit tests for signal decay function
```

**Rules**:
- Subject line: imperative mood, lowercase, no period, ≤72 chars
- Body (optional): explain *why*, not *what*. Reference PRD section if applicable.
- Breaking changes: add `BREAKING CHANGE:` footer

---

## Documentation Requirements

Documentation is not optional. Every PR must include the relevant docs updates or it is
not complete. "I'll document it later" does not exist in this project.

### Inline Code Documentation

**Python (Worker)**
- Every module: top-of-file docstring explaining purpose, inputs, outputs, and which
  PRD section it implements.
- Every function and class: docstring with Args, Returns, Raises. No one-liners for
  anything with side effects.
- Every ARQ job: docstring must include estimated runtime, retry behavior, and failure mode.
- Complex logic blocks: inline comment explaining *why*, not *what*.

```python
async def score_trend(trend: Trend, rubric: TrendRubric) -> ScoredTrend:
    """
    Apply the triage rubric to a discovered trend and return a scored result.

    Implements PRD Section 3 (Topic Triage Rubric). Scores are computed as a
    weighted sum across five dimensions: signal_strength, timing_window,
    depth_potential, novelty, and brand_fit. A trend must score >= TRIAGE_THRESHOLD
    to proceed to content generation.

    Args:
        trend: Raw trend object from the discovery layer.
        rubric: TrendRubric config loaded from environment / DB.

    Returns:
        ScoredTrend with individual dimension scores and a composite score.

    Raises:
        ScoringError: If the LLM call for brand_fit scoring fails after retries.
    """
```

**TypeScript/Next.js (Vercel)**
- Every component: JSDoc comment with description and prop types if not using TypeScript
  interfaces (but always use TypeScript interfaces).
- Every API route handler: JSDoc describing the endpoint, request shape, response shape,
  and which Worker job it triggers or reads from.
- Every utility function: JSDoc with `@param`, `@returns`, `@throws`.

```typescript
/**
 * Fetches all staged content items awaiting approval from Postgres.
 * Called by the approval UI dashboard on initial load and after each action.
 *
 * @returns Array of StagedContent items ordered by created_at desc
 * @throws DatabaseError if Postgres connection fails
 */
export async function getStagedContent(): Promise<StagedContent[]>
```

### File-Level READMEs

Every significant directory must have a `README.md`. Minimum content:

```markdown
# <directory name>

## Purpose
One paragraph. What does this directory do? Which PRD section does it implement?

## Structure
Brief description of each file / subdirectory.

## How it fits in the pipeline
Where does data come from? Where does it go next?

## Environment variables required
List any env vars this module reads.

## Running locally
Any commands needed to run or test this module in isolation.
```

Required README locations:
- `/` (root) — project overview, quick start, link to PRD
- `/worker/` — FastAPI app overview, ARQ job registry
- `/worker/jobs/` — every job file, what it does, when it runs
- `/worker/discovery/` — source adapters, polling strategy
- `/worker/generation/` — prompt architecture, platform branches
- `/app/` (Next.js root) — Vercel app overview
- `/app/api/` — all API route handlers listed with purpose
- `/docs/` — architecture diagrams, decision log

### `/docs/` Directory (maintain throughout the project)

```
/docs/
  architecture.md       ← system diagram (text-based), updated when layers change
  decisions/            ← one markdown file per architectural decision
    001-vercel-worker-split.md
    002-upstash-over-self-hosted-redis.md
    ...
  runbooks/             ← operational how-tos
    local-dev-setup.md
    deploy-worker.md
    deploy-vercel.md
    add-new-platform.md
  api/                  ← API reference
    worker-api.md
    notion-schema.md
```

**Decision doc format** (`/docs/decisions/NNN-title.md`):
```markdown
# NNN — Decision Title
_Date: YYYY-MM-DD | Status: Accepted_

## Context
What problem were we solving?

## Options Considered
1. Option A — pros / cons
2. Option B — pros / cons

## Decision
What we chose and why.

## Consequences
What this makes easier. What it makes harder. What we're deferring.
```

Write a decision doc for every non-trivial architectural choice. If you're choosing
between two reasonable approaches, that's a decision doc. The PRD debate already produced
the first set — extract them into `/docs/decisions/` as part of project setup.

### CHANGELOG.md

Maintain a `CHANGELOG.md` in the root using Keep a Changelog format:

```markdown
# Changelog

## [Unreleased]
### Added
### Changed
### Fixed

## [0.1.0] — YYYY-MM-DD
### Added
- Initial trend discovery layer (RSS + Reddit/HN)
...
```

Update `[Unreleased]` section with every PR. Move to a versioned section on release.

### Type Annotations

- Python: full type annotations on all function signatures. Use `from __future__ import annotations`.
- TypeScript: strict mode. No `any`. No `// @ts-ignore` without a comment explaining why.

---

## Environment Variables

Never hardcode. Never commit. Always document.

Every env var used anywhere in the project must appear in:
1. `.env.example` (with a placeholder value and a comment explaining what it is)
2. The README of the module that uses it
3. Vercel dashboard (for Vercel-layer vars) or Railway/Fly.io config (for Worker vars)

```bash
# .env.example — keep this in sync with reality

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...          # Claude API key

# Postgres (Vercel Postgres / Neon)
DATABASE_URL=postgresql://...          # Full connection string

# Redis (Upstash)
UPSTASH_REDIS_REST_URL=https://...    # Upstash REST URL
UPSTASH_REDIS_REST_TOKEN=...          # Upstash REST token

# Notion
NOTION_API_KEY=secret_...             # Notion integration token
NOTION_DB_ID=b6ef1af3-2b70-4346-a107-e4b21a754b3e  # Second Brain DB

# Worker
WORKER_SECRET=...                     # Shared secret for Vercel → Worker calls
ARQ_REDIS_URL=redis://...             # ARQ job queue Redis URL

# Sources
RSS_FEED_URLS=...                     # Comma-separated list of RSS feed URLs
TWITTER_BEARER_TOKEN=...              # Twitter API v2 bearer token
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
```

---

## Testing Requirements

No PR merges without tests. Minimum coverage expectations:

| Layer | What to test | Framework |
|---|---|---|
| Worker — scoring | Unit tests for rubric scoring logic | pytest |
| Worker — discovery | Unit tests with mocked HTTP responses | pytest + respx |
| Worker — generation | Prompt snapshot tests (assert structure, not exact output) | pytest |
| Worker — jobs | Integration tests against test Postgres/Redis | pytest + testcontainers |
| Vercel — API routes | Route handler unit tests | Vitest |
| Vercel — UI | Component tests for approval workflow | Vitest + Testing Library |

Test files live alongside source files: `foo.py` → `test_foo.py`, `route.ts` → `route.test.ts`.

CI runs all tests on every PR via GitHub Actions. PR cannot merge if CI is red.

---

## Brand Context

Claude Code generates content prompts and UI copy that reflect this brand. Internalize it.

- **Voice**: Intellectual stand-up comedy. Dry, direct, systems-thinker, anti-hype. Explains
  complex things simply without condescending. Uses humor to land the point.
- **Color palette**: Teal (`#00B4D8`) / Orange (`#FF6B35`)
- **Handles**: drinkYourOJ (Substack, Twitter/X, LinkedIn), drinkThatOJ (Twitch)
- **Core topics**: DePIN, decentralized infrastructure, AI tooling and critique, blockchain
  infrastructure (NOT price/speculation), community building, solopreneur/indie builder culture
- **Audience**: Technically literate but not necessarily developers. Skeptical of hype.
  Have been burned by crypto promises. Trust nuance over enthusiasm.
- **Hard filters** — never generate content that:
  - Uses "AI is changing everything" as a thesis
  - Speculates on token prices or market direction
  - Sounds like a press release or pitch deck
  - Is a bandwagon take (if everyone's writing it, we're not)
  - Uses LinkedIn hustle-porn framing

---

## Working Agreement

- Read the PRD before starting any task. The task list is in PRD Section 11.
- Read this file at the start of every session.
- If something in the PRD is ambiguous, say so and ask before implementing.
- If a decision needs to be made that isn't in the PRD, write a decision doc in
  `/docs/decisions/` and ask Justin to approve before proceeding.
- If a task will require more than one feature branch, say so upfront and get alignment
  on the split before starting.
- Don't gold-plate. Build what the PRD says. Put future ideas in PRD Section 10.
- When a feature branch is complete: summarize what was built, list files changed,
  state the PR target (`feature/x` → `develop`), and stop. Do not merge.
