"""
Signal Scoring package for the OJ Content Engine.

Implements PRD Section 3 (Topic Triage Rubric). Two-pass scoring:
  - Pass 1: Rule-based (signal strength, timing window, community resonance)
  - Pass 2: LLM-assisted (depth potential, novelty, brand angle availability)

Adjustments from the scoring_adjustments table are applied between passes.
The pipeline orchestrator computes a weighted composite score and persists
a ScoredSignal row.
"""
