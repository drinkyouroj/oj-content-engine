"""Platform-specific prompt templates for content generation.

Implements PRD Section 5 (Content Generation). Each submodule exports a
``build_prompt()`` function that assembles a user-role prompt for a single
platform. The shared brand voice bible lives in ``system.py`` and is used
as the system prompt across all platforms.

Modules:
    system    -- Brand voice bible (system prompt).
    substack  -- Substack long-form article prompts.
    twitter   -- Twitter/X thread prompts.
    linkedin  -- LinkedIn thought-leadership prompts.
    instagram -- Instagram caption + image-card prompts.
"""
from __future__ import annotations
