# worker/scoring

## Purpose
Two-pass signal scoring pipeline implementing PRD Section 3 (Topic Triage Rubric). Takes raw signals from the discovery layer, scores them across six dimensions using rule-based and LLM-assisted methods, and persists `ScoredSignal` rows for downstream triage and content generation.

## Structure

| File | Description |
|---|---|
| `rubric.py` | Constants: dimension weights, thresholds, keyword taxonomy |
| `pass1.py` | Pass 1 rule-based scoring: signal strength, timing window, community resonance |
| `pass2.py` | Pass 2 LLM-assisted scoring: depth potential, novelty, brand angle availability |
| `adjustments.py` | Applies per-keyword scoring adjustments from the `scoring_adjustments` table |
| `pipeline.py` | Orchestrates Pass 1 → adjustments → pre-filter → Pass 2 → composite → persist |
| `test_*.py` | Unit tests for each module |

## How it fits in the pipeline

```
Discovery Layer (signals table)
        │
        ▼
  Scoring Pipeline (this package)
    ├── Pass 1: rule-based (no LLM cost)
    ├── Adjustments: per-keyword tweaks from DB
    ├── Pre-filter: skip LLM if score <= 30
    ├── Pass 2: Claude Haiku scoring
    └── Composite: weighted sum → scored_signals table
        │
        ▼
  Triage / Content Generation (downstream)
```

**Data in**: `Signal` rows from the `signals` table.
**Data out**: `ScoredSignal` rows in the `scored_signals` table with `score_breakdown` JSONB and `composite_score`.

## Scoring Dimensions

| Dimension | Weight | Pass | Method |
|---|---|---|---|
| `signal_strength` | 0.25 | 1 | Cross-source corroboration count |
| `timing_window` | 0.15 | 1 | Age-based scoring with novelty cap |
| `community_resonance` | 0.10 | 1 | Keyword taxonomy matching |
| `depth_potential` | 0.15 | 2 | LLM assessment of analytical depth |
| `novelty` | 0.15 | 2 | LLM assessment of freshness |
| `brand_angle_availability` | 0.20 | 2 | LLM assessment of brand fit |

## Environment variables required

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Postgres connection string |
| `ANTHROPIC_API_KEY` | No | Claude API key for Pass 2. If empty, defaults to scores of 50. |

## Running locally

```bash
cd worker
python3.12 -m pip install -e ".[dev]"
python3.12 -m pytest scoring/ -v
```

To run the scoring ARQ job manually, enqueue `run_scoring_pipeline` via the ARQ CLI or trigger it from discovery jobs.
