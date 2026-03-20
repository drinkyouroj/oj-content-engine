"""
Topic triage engine — applies hard gates, thresholds, and creates topics.

Implements PRD Section 3 (Topic Triage Rubric). Takes scored signals and
determines their fate: queued for generation, flagged for review, or archived.
"""

from __future__ import annotations
