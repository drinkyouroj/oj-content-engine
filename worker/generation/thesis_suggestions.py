"""Thesis suggestion generation — uses Claude Haiku to propose 3-5 angles.

Fetches the full source article, combines with score breakdown and brand
context, and asks Haiku to generate thesis statement options for Justin
to choose from.

Inputs:
    - Topic with scored_signal.signal (URL, title, body_preview)
    - LLMClient configured with Anthropic API key

Outputs:
    - List of 3-5 thesis statement strings
"""
from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from worker.generation.llm_client import LLMClient, LLMGenerationError, get_model_config

logger = logging.getLogger(__name__)

_MAX_ARTICLE_CHARS = 4000

_SYSTEM_PROMPT = """\
You are a thesis generator for the drinkYourOJ content brand.

Brand context:
- Voice: Intellectual stand-up comedy. Dry, direct, systems-thinker, anti-hype.
- Core topics: AI infrastructure/critique, tech policy/regulation, DePIN, \
Seahawks/NFL analytics, media criticism, solopreneur culture.
- Audience: Technically literate, skeptical of hype, trust nuance over enthusiasm.
- Hard filters: No "AI is changing everything" breathless takes, no token price \
speculation, no press-release tone, no bandwagon takes.

Your job: generate 3-5 thesis statements for a potential drinkYourOJ article. \
Each thesis should be:
- 2-3 sentences long
- Contrarian or non-obvious — not the take everyone else is writing
- Specific enough to anchor an entire article
- Distinct from the other options — each suggests a different angle

Respond with a numbered list (1. through 5.) and nothing else. No preamble, \
no commentary, no "Here are some options:" — just the numbered theses.\
"""


async def _fetch_article(url: str) -> str:
    """Fetch and extract article body text from a URL.

    Args:
        url: Source article URL.

    Returns:
        Plain text article content, truncated to _MAX_ARTICLE_CHARS.
        Empty string if fetch or parse fails.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to fetch article %s: %s", url, exc)
        return ""

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove noise
        for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # Try common article selectors
        article = (
            soup.find("article")
            or soup.find(class_=re.compile(r"post-content|article-body|entry-content|body-markup"))
            or soup.find("main")
            or soup.body
        )

        text = article.get_text(separator="\n", strip=True) if article else ""
        return text[:_MAX_ARTICLE_CHARS]
    except Exception as exc:
        logger.warning("Failed to parse article %s: %s", url, exc)
        return ""


def _parse_theses(raw: str) -> list[str]:
    """Parse a numbered list of theses from LLM output.

    Handles formats like "1. Thesis" or "1) Thesis".
    Falls back to returning the entire response as a single thesis.

    Args:
        raw: Raw LLM response text.

    Returns:
        List of thesis strings with numbering stripped.
    """
    # Strip any leading "1. " or "1) " from the whole block before splitting
    cleaned = re.sub(r"^\s*\d+[.)]\s*", "", raw.strip())
    parts = re.split(r"\n\s*\d+[.)]\s*", cleaned)
    theses = [p.strip() for p in parts if p.strip()]

    if not theses:
        return [raw.strip()] if raw.strip() else []

    return theses


async def suggest_theses(
    topic: object,
    llm_client: LLMClient,
) -> list[str]:
    """Generate 3-5 thesis suggestions for a topic.

    Fetches the source article, combines with score breakdown, and calls
    Claude Haiku to generate thesis options.

    Args:
        topic: Topic ORM instance with scored_signal.signal loaded.
        llm_client: Configured LLMClient with Anthropic key.

    Returns:
        List of 3-5 thesis statement strings.

    Raises:
        LLMGenerationError: If the LLM call fails after retries.
    """
    signal = topic.scored_signal.signal
    scored = topic.scored_signal

    article_text = await _fetch_article(signal.url)
    if not article_text:
        logger.info("Using body_preview fallback for %s", signal.url)
        article_text = signal.body_preview or signal.title

    breakdown = scored.score_breakdown or {}
    score_lines = "\n".join(
        f"  {dim.replace('_', ' ').title()}: {score}/100"
        for dim, score in breakdown.items()
    )

    user_prompt = (
        f"Topic: {signal.title}\n"
        f"Composite Score: {scored.composite_score}\n\n"
        f"Score Breakdown:\n{score_lines}\n\n"
        f"Source Article:\n{article_text}\n\n"
        f"Generate 3-5 thesis statements for a drinkYourOJ article about this topic."
    )

    config = get_model_config("thesis_suggest")
    response = await llm_client.generate(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        provider=config["provider"],
        model=config["model"],
        max_tokens=1024,
        temperature=0.8,
    )

    theses = _parse_theses(response.content)
    logger.info("Generated %d thesis suggestions for topic %s", len(theses), topic.id)
    return theses
