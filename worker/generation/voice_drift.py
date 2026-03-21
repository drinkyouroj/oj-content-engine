"""Substack voice-drift self-critique — dedicated second pass.

Reads a generated Substack draft and flags sentences that sound generic,
off-brand, or like a press release. Rewrites flagged sentences in
Justin's voice. Returns the revised draft.

Only used for Substack long-form. Other platforms skip this.
"""
from __future__ import annotations

import logging

from worker.generation.llm_client import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

_CRITIQUE_SYSTEM_PROMPT = """\
You are a drinkYourOJ subscriber who has read every post since 2023. You know \
Justin's voice intimately: dry, direct, systems-thinking, occasionally funny, \
never breathless.

Your job is to review a draft article and produce a REVISED version. \
Do NOT output commentary or analysis. Output ONLY the full revised article.

For every sentence that sounds like it could appear in a generic tech newsletter, \
a press release, or a crypto hype blog, rewrite it in Justin's voice.

Self-review checklist — fix all violations silently:
- No em dashes (—)
- No banned words: delve, tapestry, vibrant, landscape, realm, embark, moreover, \
notably, pivotal, arguably
- No banned phrases: "Everyone wants to", "Without further ado", "Have you ever wondered", \
"Picture this"
- No excessive parallelism: "It's not about X, it's about Y"
- No passive constructions that hide the actor
- Sentence beginnings must vary (prepositional phrases, rhetorical questions, \
adverbs, one-word beats)
- Every abstract concept needs a concrete metaphor
- Active voice; name the actor
- Technical terms defined before use
- No concept explained twice
- Ending: thought-provoking question OR clear point, not both

IMPORTANT — preserve these structural elements exactly:
- TITLE: and SUBTITLE: lines at the top
- All [IMAGE:], [ALT:], and [CAPTION:] markers
- All inline footnote markers like [1], [2], [3]
- The SOURCES: section at the end with all source URLs

Output the full revised article in the same format as the input. Nothing else.\
"""


async def run_voice_critique(
    draft: str,
    llm_client: LLMClient,
    provider: str,
    model: str,
) -> LLMResponse:
    """Run voice-drift self-critique on a Substack draft.

    Args:
        draft: The generated Substack article text.
        llm_client: LLMClient instance.
        provider: Provider name for the critique model.
        model: Model identifier for the critique.

    Returns:
        LLMResponse with revised draft content.

    Raises:
        LLMGenerationError: If the critique LLM call fails.
    """
    logger.info("Running voice-drift critique (%s/%s)", provider, model)

    return await llm_client.generate(
        system_prompt=_CRITIQUE_SYSTEM_PROMPT,
        user_prompt=f"Review and revise this draft:\n\n{draft}",
        provider=provider,
        model=model,
        max_tokens=8192,
        temperature=0.5,
    )
