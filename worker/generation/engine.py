"""Content generation engine orchestrator.

Ties together vertical detection, exemplar selection, prompt assembly,
LLM generation, and voice-drift critique to produce ContentDraft rows
for all four platforms (Substack, Twitter/X, LinkedIn, Instagram).

Implements PRD Section 4 (Content Generation Engine).

Inputs:
    - Topic with nested ScoredSignal -> Signal
    - AsyncSession for database operations
    - LLMClient for LLM calls

Outputs:
    - List of ContentDraft instances (one per successfully generated platform)

Environment variables:
    See worker/generation/llm_client.py for model routing overrides.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.content_draft import ContentDraft, DraftStatus, Platform
from worker.app.models.system_alert import SystemAlert
from worker.app.models.topic import Topic, TopicStatus
from worker.generation.exemplar_selector import select_exemplars
from worker.generation.llm_client import LLMClient, LLMGenerationError, get_model_config
from worker.generation.prompts.instagram import build_prompt as build_instagram_prompt
from worker.generation.prompts.linkedin import build_prompt as build_linkedin_prompt
from worker.generation.prompts.substack import build_prompt as build_substack_prompt
from worker.generation.prompts.system import build_system_prompt
from worker.generation.prompts.twitter import build_prompt as build_twitter_prompt
from worker.generation.verticals import detect_vertical
from worker.generation.voice_drift import run_voice_critique

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform -> prompt builder mapping
# ---------------------------------------------------------------------------

_PLATFORM_BUILDERS = {
    Platform.SUBSTACK: build_substack_prompt,
    Platform.TWITTER: build_twitter_prompt,
    Platform.LINKEDIN: build_linkedin_prompt,
    Platform.INSTAGRAM: build_instagram_prompt,
}

# Rough cost-per-token estimates by provider (USD)
_TOKEN_COST_RATES: dict[str, float] = {
    "groq": 0.0,
    "anthropic": 0.000008,  # ~$8/1M tokens blended estimate
}


def _estimate_token_cost(total_tokens: int, provider: str) -> float:
    """Estimate USD cost from token count and provider.

    Args:
        total_tokens: Combined input + output tokens.
        provider: LLM provider name.

    Returns:
        Estimated cost in USD. Groq is free-tier, so returns 0.0.
    """
    rate = _TOKEN_COST_RATES.get(provider, 0.0)
    return round(total_tokens * rate, 4)


def _prompt_version_hash(prompt: str) -> str:
    """Generate a short hash of a prompt template for tracking.

    Args:
        prompt: The assembled prompt string.

    Returns:
        First 8 characters of the SHA-256 hex digest.
    """
    return hashlib.sha256(prompt.encode()).hexdigest()[:8]


async def generate_for_topic(
    topic: Topic,
    session: AsyncSession,
    llm_client: LLMClient,
) -> list[ContentDraft]:
    """Generate content drafts for all platforms from a triaged topic.

    Orchestration flow:
    1. Detect topic vertical from title/body keywords.
    2. Select 3-5 voice exemplars by vertical match.
    3. For each platform, build prompts, call LLM, optionally run voice-drift
       critique (Substack only), and create a ContentDraft row.
    4. On per-platform LLM failure: log, create a SystemAlert, skip, continue.

    Implements PRD Section 4 (Content Generation Engine).

    Args:
        topic: Topic instance with nested scored_signal -> signal.
        session: Async database session for persisting drafts and alerts.
        llm_client: Configured LLMClient for generation calls.

    Returns:
        List of ContentDraft instances that were successfully created.
        May be fewer than 4 if some platforms failed.

    Raises:
        No exceptions are raised to the caller. Per-platform failures are
        logged and recorded as SystemAlert rows.
    """
    signal = topic.scored_signal.signal
    title = signal.title
    body = signal.body_preview or ""
    score_breakdown = topic.scored_signal.score_breakdown
    thesis = topic.thesis

    # Step 1: Detect vertical
    vertical = detect_vertical(title, body)
    topic.vertical = vertical
    logger.info("Detected vertical=%s for topic=%s", vertical, topic.id)

    # Step 2: Update topic status to GENERATING
    topic.status = TopicStatus.GENERATING

    # Step 3: Build system prompt (shared across platforms)
    system_prompt = build_system_prompt()

    drafts: list[ContentDraft] = []

    for platform, build_prompt in _PLATFORM_BUILDERS.items():
        platform_key = platform.value  # e.g. "substack"

        try:
            # 3a: Get model config
            config = get_model_config(platform_key)
            provider = config["provider"]
            model = config["model"]

            # 3b: Select exemplars for this platform
            exemplars = await select_exemplars(session, platform_key, vertical)
            exemplar_texts = [e.content for e in exemplars]

            # 3c: Build platform-specific user prompt
            user_prompt = build_prompt(
                topic_title=title,
                topic_body=body,
                score_breakdown=score_breakdown,
                thesis=thesis,
                exemplars=exemplar_texts,
            )

            # 3d: Call LLM
            response = await llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                provider=provider,
                model=model,
            )

            content = response.content
            total_tokens = response.total_tokens

            # 3e: Substack-only voice-drift critique
            voice_drift_applied = False
            if platform == Platform.SUBSTACK:
                critique_config = get_model_config("substack_critique")
                critique_response = await run_voice_critique(
                    draft=content,
                    llm_client=llm_client,
                    provider=critique_config["provider"],
                    model=critique_config["model"],
                )
                content = critique_response.content
                total_tokens += critique_response.total_tokens
                voice_drift_applied = True

            # 3f: Build generation metadata
            generation_metadata: dict = {
                "prompt_version": _prompt_version_hash(user_prompt),
            }
            if not topic.thesis_provided:
                generation_metadata["ai_originated"] = True
            if not exemplars:
                generation_metadata["no_exemplars_available"] = True
            if voice_drift_applied:
                generation_metadata["voice_drift_applied"] = True

            # 3g: Create ContentDraft
            draft = ContentDraft(
                topic_id=topic.id,
                platform=platform,
                content=content,
                status=DraftStatus.DRAFT,
                model_used=f"{provider}/{model}",
                token_cost=_estimate_token_cost(total_tokens, provider),
                generated_at=datetime.now(timezone.utc),
                generation_metadata=generation_metadata,
            )
            session.add(draft)
            drafts.append(draft)

            logger.info(
                "Generated %s draft for topic=%s (tokens=%d)",
                platform_key, topic.id, total_tokens,
            )

        except (LLMGenerationError, Exception) as exc:  # noqa: BLE001
            logger.error(
                "Failed to generate %s draft for topic=%s: %s",
                platform_key, topic.id, exc,
            )
            alert = SystemAlert(
                source=f"generation/{platform_key}",
                alert_type="generation_failure",
                consecutive_failures=1,
                last_failure_at=datetime.now(timezone.utc),
            )
            session.add(alert)

    # Step 4: Update topic status to GENERATED
    topic.status = TopicStatus.GENERATED

    logger.info(
        "Generation complete for topic=%s: %d/%d platforms succeeded",
        topic.id, len(drafts), len(_PLATFORM_BUILDERS),
    )

    return drafts
