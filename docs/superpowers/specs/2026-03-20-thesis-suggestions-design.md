# Thesis Suggestions Design

**Goal:** Generate 3-5 thesis statement options for a topic using Claude Haiku 4.5, based on the full source article and scoring data, so Justin can pick and edit one instead of writing from scratch.

**Scope:** One new Worker endpoint, one Next.js proxy route, one UI update to the existing thesis input component.

**Depends on:** Approval UI (Wave 4b), content generation engine (Wave 4a).

---

## 1. Architecture

The thesis suggestion flow:

```
[Review Page] → "Suggest Theses" button
    → POST /api/suggest-theses (Next.js proxy)
    → POST /api/suggest-theses/{topic_id} (Worker)
    → Worker fetches source article via httpx
    → Worker assembles prompt: article + score breakdown + brand context
    → Worker calls Anthropic Claude Haiku 4.5
    → Returns 3-5 thesis strings as JSON
    → UI renders clickable thesis cards
    → User clicks one → populates thesis textarea for editing
```

**Why Worker-side, not Next.js?** Article fetching + LLM call could take 5-15 seconds. The Worker has no timeout constraints. The Next.js layer just proxies.

---

## 2. Worker: Thesis Suggestion Module

### New file: `worker/generation/thesis_suggestions.py`

**`suggest_theses(topic, session) -> list[str]`**

Steps:
1. Load signal URL from `topic.scored_signal.signal.url`
2. Fetch the full article via `httpx.AsyncClient.get(url)` with 10s timeout
3. Parse HTML with BeautifulSoup — extract article body text (strip nav, scripts, ads)
4. Truncate to ~4,000 chars to stay within Haiku's sweet spot
5. If fetch fails (timeout, 404, parse error): fall back to `signal.body_preview`
6. Assemble prompt with:
   - Article text (or body_preview fallback)
   - Score breakdown (all 6 dimensions with scores)
   - Brand angle description (from Pass 2 scoring, if available)
   - Brand context (voice description, core topics, audience)
7. Call `LLMClient.generate()` with provider=anthropic, model=claude-haiku-4-5
8. Parse response — expect numbered list of 3-5 thesis statements
9. Return list of thesis strings

**LLM prompt structure:**

System prompt: Brand context (drinkYourOJ voice, audience, hard filters). Instructions to generate 3-5 thesis statements that are contrarian, specific, and anchored in the source material. Each thesis should be 2-3 sentences and suggest a distinct angle.

User prompt: Article text + score breakdown + "Generate 3-5 thesis statements for a drinkYourOJ article about this topic."

**Response parsing:** Split on numbered lines (`1.`, `2.`, etc.) or newlines. Strip numbering. Return clean strings. If parsing fails, return the raw response as a single thesis.

### New file: `worker/generation/test_thesis_suggestions.py`

Tests with mocked httpx and LLM client:
- Happy path: article fetched, 5 theses returned
- Fetch failure: falls back to body_preview, still generates theses
- LLM returns unexpected format: graceful degradation
- Empty article: uses body_preview

---

## 3. Worker: API Endpoint

### New endpoint on FastAPI: `POST /api/suggest-theses/{topic_id}`

- Authenticates via `x-worker-secret` header (same as regenerate)
- Loads topic with scored_signal and signal via `_session_factory`
- Calls `suggest_theses(topic, session)`
- Returns `{ theses: ["thesis 1", "thesis 2", ...] }`
- On error: returns `{ error: "message" }` with status 500

---

## 4. Next.js: Proxy Route

### New file: `app/api/suggest-theses/route.ts`

Same pattern as `/api/regenerate`:
- Parse `{ topicId }` from body
- Forward to `{WORKER_URL}/api/suggest-theses/{topicId}` with `WORKER_SECRET` header
- Return the Worker's JSON response
- On Worker error: return `{ theses: [], error: "message" }`

---

## 5. UI: Thesis Input Update

### Modify: `components/thesis-input.tsx`

Add to the existing component (when thesis is not yet provided):

1. **"Suggest Theses" button** — styled as secondary/outline, below the textarea
2. **Loading state** — "Generating suggestions..." with spinner, button disabled
3. **Thesis cards** — 3-5 cards, each showing the thesis text. Styled as `bg-zinc-800` with hover highlight and teal border on hover. Clicking a card populates the textarea with that thesis text.
4. **Flow:** Button click → API call → cards appear → user clicks card → textarea populated → user edits → saves normally via existing "Save Thesis" button

The cards appear between the button and the textarea. The user can:
- Click a card to populate the textarea, then edit and save
- Ignore the suggestions and type their own thesis
- Click "Suggest Theses" again for new suggestions

---

## 6. Model Configuration

Default model: `anthropic/claude-haiku-4-5`

Added to `GENERATION_MODELS` in `llm_client.py`:
```python
"thesis_suggest": {"provider": "anthropic", "model": "claude-haiku-4-5"},
```

Overridable via `GENERATION_MODEL_THESIS_SUGGEST` env var.

---

## 7. Dependencies

No new packages — httpx, beautifulsoup4, and anthropic are already installed.

---

## 8. Testing

| Module | Tests | Approach |
|--------|-------|----------|
| `thesis_suggestions.py` | 4+ | Mock httpx + LLM client, verify prompt assembly and response parsing |
| `suggest-theses` Worker endpoint | - | Tested via integration (proxy route) |
| `suggest-theses` Next.js route | - | Same proxy pattern as regenerate, already proven |
| `thesis-input.tsx` | - | Manual UI testing (click flow) |

---

## 9. Files Changed

**New:**
- `worker/generation/thesis_suggestions.py`
- `worker/generation/test_thesis_suggestions.py`
- `app/api/suggest-theses/route.ts`

**Modified:**
- `worker/app/main.py` — add suggest-theses endpoint
- `worker/generation/llm_client.py` — add `thesis_suggest` to GENERATION_MODELS
- `components/thesis-input.tsx` — add suggest button + thesis cards
- `lib/worker-client.ts` — add `suggestTheses()` function
