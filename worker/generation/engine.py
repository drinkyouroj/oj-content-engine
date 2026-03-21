"""Content generation engine orchestrator.

Implements a two-phase generation flow:

Phase 1 (automatic): Topic -> Thesis -> Substack article only.
    Called by the ARQ generation job when topics are queued.

Phase 2 (on-demand): Substack -> Social platform content.
    Called per-platform when Justin clicks "Generate" on the dashboard.
    Uses the Substack article as source context so social posts are
    derivative of the long-form piece.

Implements PRD Section 4 (Content Generation Engine).

Inputs:
    - Topic with nested ScoredSignal -> Signal
    - AsyncSession for database operations
    - LLMClient for LLM calls

Outputs:
    - ContentDraft instances

Environment variables:
    See worker/generation/llm_client.py for model routing overrides.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.content_draft import ContentDraft, DraftStatus, Platform
from worker.app.models.signal import Signal
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


def get_signal(topic: Topic) -> "Signal":
    """Get the signal for a topic, whether steered or discovered.

    Steered topics have a direct signal_id (no scored_signal). Discovered
    topics reach their signal through scored_signal.signal. This helper
    abstracts that difference so callers don't need to branch.

    Args:
        topic: Topic ORM instance with relationships loaded.

    Returns:
        The Signal instance associated with the topic.

    Raises:
        ValueError: If neither signal_id nor scored_signal_id is set.
    """

    if topic.signal is not None:
        return topic.signal
    if topic.scored_signal is not None:
        return topic.scored_signal.signal
    raise ValueError(
        f"Topic {topic.id} has no signal (neither signal_id nor scored_signal_id set)"
    )

# ---------------------------------------------------------------------------
# Platform -> prompt builder mapping (social platforms only)
# ---------------------------------------------------------------------------

_SOCIAL_PLATFORM_BUILDERS = {
    Platform.TWITTER: build_twitter_prompt,
    Platform.LINKEDIN: build_linkedin_prompt,
    Platform.INSTAGRAM: build_instagram_prompt,
}

# Rough cost-per-token estimates by provider (USD)
_TOKEN_COST_RATES: dict[str, float] = {
    "groq": 0.0,
    "anthropic": 0.000008,  # ~$8/1M tokens blended (Sonnet); Haiku is ~$1/1M
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
    """Generate Substack draft only from a triaged topic (Phase 1).

    Orchestration flow:
    1. Detect topic vertical from title/body keywords.
    2. Select 3-5 voice exemplars by vertical match.
    3. Build Substack prompt, call LLM, run voice-drift critique.
    4. Create a ContentDraft row for the Substack article.

    Social platform content (Twitter, LinkedIn, Instagram) is NOT generated
    here. Those are generated on-demand via generate_social_for_topic() when
    the reviewer explicitly requests them from the dashboard.

    Implements PRD Section 4 (Content Generation Engine).

    Args:
        topic: Topic instance with nested scored_signal -> signal.
        session: Async database session for persisting drafts and alerts.
        llm_client: Configured LLMClient for generation calls.

    Returns:
        List containing the Substack ContentDraft if successful, empty on failure.

    Raises:
        No exceptions are raised to the caller. Failures are logged and
        recorded as SystemAlert rows.
    """
    signal = get_signal(topic)
    title = signal.title
    body = signal.body_preview or ""
    score_breakdown = topic.scored_signal.score_breakdown if topic.scored_signal else {}
    thesis = topic.thesis

    # Collect source URLs for citation
    source_urls: list[str] = []
    if signal.source_metrics and isinstance(signal.source_metrics, dict):
        source_urls = signal.source_metrics.get("source_urls", [])
    if not source_urls and signal.url:
        source_urls = [signal.url]

    # Step 1: Detect vertical
    vertical = detect_vertical(title, body)
    topic.vertical = vertical
    logger.info("Detected vertical=%s for topic=%s", vertical, topic.id)

    # Step 2: Update topic status to GENERATING
    topic.status = TopicStatus.GENERATING

    # Step 3: Build system prompt
    system_prompt = build_system_prompt()

    drafts: list[ContentDraft] = []

    try:
        # 3a: Get model config for Substack
        config = get_model_config("substack")
        provider = config["provider"]
        model = config["model"]

        # 3b: Select exemplars
        exemplars = await select_exemplars(session, "substack", vertical)
        exemplar_texts = [e.content for e in exemplars]

        # 3c: Build Substack prompt
        user_prompt = build_substack_prompt(
            topic_title=title,
            topic_body=body,
            score_breakdown=score_breakdown,
            thesis=thesis,
            exemplars=exemplar_texts,
            source_urls=source_urls,
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

        # 3e: Voice-drift critique (Substack always gets this)
        critique_config = get_model_config("substack_critique")
        critique_response = await run_voice_critique(
            draft=content,
            llm_client=llm_client,
            provider=critique_config["provider"],
            model=critique_config["model"],
        )
        content = critique_response.content
        total_tokens += critique_response.total_tokens

        # 3f: Build generation metadata
        generation_metadata: dict = {
            "prompt_version": _prompt_version_hash(user_prompt),
            "voice_drift_applied": True,
        }
        if not topic.thesis_provided:
            generation_metadata["ai_originated"] = True
        if not exemplars:
            generation_metadata["no_exemplars_available"] = True

        # 3g: Create ContentDraft
        draft = ContentDraft(
            topic_id=topic.id,
            platform=Platform.SUBSTACK,
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
            "Generated substack draft for topic=%s (tokens=%d)",
            topic.id, total_tokens,
        )

    except (LLMGenerationError, Exception) as exc:  # noqa: BLE001
        logger.error(
            "Failed to generate substack draft for topic=%s: %s",
            topic.id, exc,
        )
        alert = SystemAlert(
            source="generation/substack",
            alert_type="generation_failure",
            consecutive_failures=1,
            last_failure_at=datetime.now(timezone.utc),
        )
        session.add(alert)

    # Step 4: Update topic status to GENERATED
    topic.status = TopicStatus.GENERATED

    logger.info(
        "Generation complete for topic=%s: substack %s",
        topic.id, "succeeded" if drafts else "failed",
    )

    return drafts


async def generate_social_for_topic(
    topic: Topic,
    platform: Platform,
    substack_content: str,
    session: AsyncSession,
    llm_client: LLMClient,
) -> ContentDraft:
    """Generate a single social platform draft using the Substack article as context (Phase 2).

    Called on-demand when Justin clicks a "Generate [Platform]" button on the
    review dashboard. Uses Claude Haiku 4.5 and injects the full Substack
    article so the social content is derived from the long-form piece.

    Args:
        topic: Topic instance with nested scored_signal -> signal.
        platform: Target social platform (TWITTER, LINKEDIN, or INSTAGRAM).
        substack_content: The full generated Substack article text.
        session: Async database session for persisting the draft.
        llm_client: Configured LLMClient for generation calls.

    Returns:
        The created ContentDraft instance.

    Raises:
        ValueError: If the platform is SUBSTACK (use generate_for_topic instead).
        LLMGenerationError: If the LLM call fails after retries.
    """
    if platform == Platform.SUBSTACK:
        raise ValueError("Use generate_for_topic() for Substack generation.")

    if platform not in _SOCIAL_PLATFORM_BUILDERS:
        raise ValueError(f"Unknown social platform: {platform}")

    signal = get_signal(topic)
    title = signal.title
    body = signal.body_preview or ""
    score_breakdown = topic.scored_signal.score_breakdown if topic.scored_signal else {}
    thesis = topic.thesis
    vertical = topic.vertical or detect_vertical(title, body)

    build_prompt = _SOCIAL_PLATFORM_BUILDERS[platform]
    platform_key = platform.value

    # Get model config (Haiku 4.5 for all social platforms)
    config = get_model_config(platform_key)
    provider = config["provider"]
    model = config["model"]

    # Select exemplars
    exemplars = await select_exemplars(session, platform_key, vertical)
    exemplar_texts = [e.content for e in exemplars]

    # Build system prompt
    system_prompt = build_system_prompt()

    # Build platform-specific prompt with Substack content as context
    user_prompt = build_prompt(
        topic_title=title,
        topic_body=body,
        score_breakdown=score_breakdown,
        thesis=thesis,
        exemplars=exemplar_texts,
        substack_content=substack_content,
    )

    # Call LLM
    response = await llm_client.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        provider=provider,
        model=model,
    )

    # Build generation metadata
    generation_metadata: dict = {
        "prompt_version": _prompt_version_hash(user_prompt),
        "derived_from_substack": True,
    }
    if not topic.thesis_provided:
        generation_metadata["ai_originated"] = True
    if not exemplars:
        generation_metadata["no_exemplars_available"] = True

    # Create ContentDraft
    draft = ContentDraft(
        topic_id=topic.id,
        platform=platform,
        content=response.content,
        status=DraftStatus.DRAFT,
        model_used=f"{provider}/{model}",
        token_cost=_estimate_token_cost(response.total_tokens, provider),
        generated_at=datetime.now(timezone.utc),
        generation_metadata=generation_metadata,
    )
    session.add(draft)

    logger.info(
        "Generated %s draft for topic=%s (tokens=%d, derived from substack)",
        platform_key, topic.id, response.total_tokens,
    )

    return draft
