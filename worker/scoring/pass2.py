"""
Pass 2 — LLM-assisted scoring for Depth Potential, Novelty, and Brand Angle.

Implements PRD Section 3 (Topic Triage Rubric), Pass 2.
Uses Claude Haiku to evaluate subjective dimensions that require understanding
of the drinkYourOJ brand voice and content niche. Only called if the signal
passes the Pass 1 pre-filter threshold.

Inputs:
    - Signal ORM instance (title, body_preview, source, source_metrics).
    - Anthropic API key string.

Outputs:
    - Dictionary with keys: depth_potential, novelty, brand_angle_availability.
      Each value is an integer 0-100.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic


class LLMScoringError(Exception):
    """Raised when LLM scoring fails after all retries."""

logger = logging.getLogger(__name__)

# Model used for scoring — Haiku for speed and cost efficiency
_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are a scoring assistant for the drinkYourOJ content brand.

Brand context:
- Voice: Intellectual stand-up comedy. Dry, direct, systems-thinker, anti-hype.
- Core topics: DePIN, decentralized infrastructure, AI tooling/critique, \
blockchain infrastructure (NOT price/speculation), community building, \
solopreneur/indie builder culture.
- Audience: Technically literate, skeptical of hype, trust nuance over enthusiasm.
- Hard filters: No "AI is changing everything" takes, no token price speculation, \
no press-release tone, no bandwagon takes, no LinkedIn hustle-porn.

Your job is to score a discovered signal on three dimensions (0-100 each):

1. **depth_potential**: How much substantive, original analysis can drinkYourOJ \
extract from this topic? High scores for topics with technical depth, contrarian \
angles, or systemic implications. Low for shallow news or commodity takes.

2. **novelty**: How fresh is this angle? High if few creators have covered it or \
if there's a non-obvious framing. Low if it's already saturated or a recycled take.

3. **brand_angle_availability**: How naturally does this fit drinkYourOJ's voice \
and niche? High if there's a clear DePIN/infra/AI-tooling angle with room for \
dry humor and systems thinking. Low if it's off-brand or requires forced framing.

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "depth_potential": <int 0-100>,
  "novelty": <int 0-100>,
  "brand_angle_availability": <int 0-100>,
  "brand_angle_description": "<one sentence describing the angle>"
}
"""

_MAX_RETRIES = 3
_DEFAULT_SCORES: dict[str, int] = {
    "depth_potential": 50,
    "novelty": 50,
    "brand_angle_availability": 50,
}


async def score_with_llm(
    signal: Any,
    anthropic_api_key: str,
) -> dict[str, int]:
    """Score a signal using Claude Haiku for subjective dimensions.

    Calls the Anthropic API with signal context and parses the JSON response.
    Retries up to 3 times with exponential backoff on transient failures.
    Returns default scores (all 50) if the API key is empty.

    Args:
        signal: Signal ORM instance with title, body_preview, source,
            and source_metrics attributes.
        anthropic_api_key: Anthropic API key. If empty, returns defaults.

    Returns:
        Dictionary with depth_potential, novelty, brand_angle_availability
        as integers 0-100.

    Raises:
        No exceptions are raised; failures are logged and defaults returned.
    """
    if not anthropic_api_key:
        logger.warning(
            "Anthropic API key is empty — returning default Pass 2 scores "
            "for signal %s",
            getattr(signal, "id", "unknown"),
        )
        return dict(_DEFAULT_SCORES)

    user_prompt = _build_user_prompt(signal)

    import asyncio

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return await _call_llm(anthropic_api_key, user_prompt)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            wait = 2**attempt  # 1s, 2s, 4s
            logger.warning(
                "Pass 2 LLM scoring attempt %d/%d failed: %s. Retrying in %ds.",
                attempt + 1,
                _MAX_RETRIES,
                exc,
                wait,
            )
            await asyncio.sleep(wait)

    logger.error(
        "Pass 2 LLM scoring failed after %d retries for signal %s: %s",
        _MAX_RETRIES,
        getattr(signal, "id", "unknown"),
        last_error,
    )
    raise LLMScoringError(
        f"LLM scoring failed after {_MAX_RETRIES} retries: {last_error}"
    ) from last_error


def _build_user_prompt(signal: Any) -> str:
    """Build the user prompt from signal attributes.

    Args:
        signal: Signal ORM instance.

    Returns:
        Formatted prompt string with signal details.
    """
    source = getattr(signal, "source", "unknown")
    if hasattr(source, "value"):
        source = source.value

    metrics_str = ""
    if signal.source_metrics:
        metrics_str = json.dumps(signal.source_metrics)

    return (
        f"Title: {signal.title}\n"
        f"Source: {source}\n"
        f"Body preview: {signal.body_preview or '(none)'}\n"
        f"Source metrics: {metrics_str or '(none)'}"
    )


async def _call_llm(api_key: str, user_prompt: str) -> dict[str, int]:
    """Make the Anthropic API call and parse the response.

    Args:
        api_key: Valid Anthropic API key.
        user_prompt: Formatted user prompt string.

    Returns:
        Parsed scoring dictionary.

    Raises:
        anthropic.APIError: On API failures.
        ValueError: If the response cannot be parsed as valid JSON.
        KeyError: If required keys are missing from the response.
    """
    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()
    parsed = json.loads(raw_text)

    # Validate and extract required keys
    result: dict[str, int] = {}
    for key in ("depth_potential", "novelty", "brand_angle_availability"):
        value = parsed[key]
        result[key] = max(0, min(100, int(value)))

    return result
