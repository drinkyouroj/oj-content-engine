"""
Pass 2 — LLM-assisted scoring for Depth Potential, Novelty, and Brand Angle.

Implements PRD Section 3 (Topic Triage Rubric), Pass 2.
Uses Groq (fast inference) to evaluate subjective dimensions that require
understanding of the drinkYourOJ brand voice and content niche. Only called
if the signal passes the Pass 1 pre-filter threshold.

Inputs:
    - Signal ORM instance (title, body_preview, source, source_metrics).
    - Groq API key string.

Outputs:
    - Dictionary with keys: depth_potential, novelty, brand_angle_availability.
      Each value is an integer 0-100.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from groq import AsyncGroq

logger = logging.getLogger(__name__)


class LLMScoringError(Exception):
    """Raised when LLM scoring fails after all retries."""


# Model used for scoring — fast and cheap via Groq
_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """\
You are a scoring assistant for the drinkYourOJ content brand.

Brand context:
- Voice: Intellectual stand-up comedy. Dry, direct, systems-thinker, anti-hype.
- Core topics: AI infrastructure and critique (how it actually works, who controls it, \
what breaks), tech policy and regulation, DePIN and decentralized infrastructure, \
the politics of platforms, solopreneur/indie builder culture.
- Audience: Technically literate, skeptical of hype, trust nuance over enthusiasm. \
People who build things and want to understand the systems they build on.
- Hard filters: No "AI is changing everything" breathless takes, no token price \
speculation, no press-release tone, no bandwagon takes, no LinkedIn hustle-porn. \
We want the take nobody else is writing.

Your job is to score a discovered signal on three dimensions (0-100 each):

1. **depth_potential**: How much substantive, original analysis can drinkYourOJ \
extract from this topic? High for: technical deep-dives, policy implications, \
contrarian infrastructure takes, systemic critiques. Low for: shallow news, \
product announcements, commodity takes everyone is writing.

2. **novelty**: How fresh is this angle? High if few creators have covered it, \
there's a non-obvious framing, or it connects dots others haven't. \
Low if it's already saturated or a recycled take.

3. **brand_angle_availability**: How naturally does this fit drinkYourOJ's voice? \
High if there's a clear AI/policy/infra angle with room for dry humor and \
systems thinking. Low if it's off-brand or requires forced framing.

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
    llm_api_key: str,
) -> dict[str, int]:
    """Score a signal using Groq LLM for subjective dimensions.

    Calls the Groq API with signal context and parses the JSON response.
    Retries up to 3 times with exponential backoff on transient failures.
    Returns default scores (all 50) if the API key is empty.

    Args:
        signal: Signal ORM instance with title, body_preview, source,
            and source_metrics attributes.
        llm_api_key: Groq API key. If empty, returns defaults.

    Returns:
        Dictionary with depth_potential, novelty, brand_angle_availability
        as integers 0-100.

    Raises:
        LLMScoringError: If all retry attempts fail.
    """
    if not llm_api_key:
        logger.warning(
            "LLM API key is empty — returning default Pass 2 scores "
            "for signal %s",
            getattr(signal, "id", "unknown"),
        )
        return dict(_DEFAULT_SCORES)

    user_prompt = _build_user_prompt(signal)

    import asyncio

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return await _call_llm(llm_api_key, user_prompt)
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
    """Make the Groq API call and parse the response.

    Args:
        api_key: Valid Groq API key.
        user_prompt: Formatted user prompt string.

    Returns:
        Parsed scoring dictionary.

    Raises:
        ValueError: If the response cannot be parsed as valid JSON.
        KeyError: If required keys are missing from the response.
    """
    client = AsyncGroq(api_key=api_key)
    response = await client.chat.completions.create(
        model=_MODEL,
        max_tokens=256,
        temperature=0.3,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    raw_text = response.choices[0].message.content.strip()
    # Strip markdown code fences if present (```json ... ```)
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        raw_text = raw_text.rsplit("```", 1)[0]
        raw_text = raw_text.strip()
    parsed = json.loads(raw_text)

    # Validate and extract required keys
    result: dict[str, int] = {}
    for key in ("depth_potential", "novelty", "brand_angle_availability"):
        value = parsed[key]
        result[key] = max(0, min(100, int(value)))

    return result
