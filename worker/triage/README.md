# triage

## Purpose

Applies the scoring rubric to create Topic rows from scored signals. Implements the triage decision logic described in PRD Section 3.

## Structure

- `engine.py` — Hard gates, threshold logic, status determination, and batch triage orchestration.
- `test_engine.py` — Unit tests for triage scoring and gate logic.

## How It Fits in the Pipeline

```
discovery → scoring → **triage** → generation
```

Triage receives scored signals and determines which become Topics:

- **Composite score >= 65** → Status: `queued` (proceeds to generation)
- **Composite score 55-64** → Status: `review` (held for human review in dashboard)
- **Composite score < 55** → Status: `archived` (dropped)

### Hard Gates

A signal is auto-rejected regardless of composite score if:

- `community_resonance < 20`
- `brand_angle < 20`

## Environment Variables

None specific to this module. Uses the shared `DATABASE_URL` for writing Topic rows.

## Running Locally

```bash
cd worker && python -m pytest triage/test_engine.py -v
```
