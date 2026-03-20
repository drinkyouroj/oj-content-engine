"""LinkedIn thought-leadership prompt template.

Implements PRD Section 5 (Content Generation) for the LinkedIn platform.
Generates 300-600 word posts with an opening hook, insight paragraphs, and
a closing thought. Explicitly avoids hustle-porn and corporate glaze.

Exports:
    build_prompt(topic_title, topic_body, score_breakdown, thesis, exemplars) -> str
"""
from __future__ import annotations

from worker.generation.prompts._shared import format_topic_context


def build_prompt(
    topic_title: str,
    topic_body: str,
    score_breakdown: dict[str, int],
    thesis: str | None,
    exemplars: list[str],
) -> str:
    """Assemble a LinkedIn post generation prompt.

    Args:
        topic_title: Title of the triaged topic.
        topic_body: Body preview or summary of the topic.
        score_breakdown: Dict mapping rubric dimensions to integer scores (0-100).
        thesis: Human-supplied thesis angle, or None for AI-originated content.
        exemplars: List of exemplar content strings for voice calibration.

    Returns:
        Formatted prompt string ready to pass as the user message.
    """
    sections: list[str] = []

    sections.append(format_topic_context(topic_title, topic_body, score_breakdown))
    sections.append(_format_thesis(thesis))

    if exemplars:
        sections.append(_format_exemplars(exemplars))

    sections.append(_PLATFORM_INSTRUCTIONS)

    return "\n\n".join(sections)


def _format_thesis(thesis: str | None) -> str:
    if thesis:
        return f"== THESIS ==\n\nBuild the post around this angle:\n{thesis}"
    return (
        "== THESIS ==\n\n"
        "No thesis provided. This is AI-originated content that will need "
        "heavy editing. Generate your best professional angle based on the "
        "topic, but note that no human editorial direction was given."
    )


def _format_exemplars(exemplars: list[str]) -> str:
    header = (
        "== VOICE REFERENCE EXAMPLES ==\n\n"
        "These examples show the writing STYLE only. Ignore their subject matter. "
        "Study tone, directness, and humor. LinkedIn voice should still sound like "
        "you, not like LinkedIn. Honest, direct, a little irreverent.\n\n"
        "DO NOT write about the subjects in these examples. Write about the TOPIC above.\n"
    )
    truncated = []
    for i, ex in enumerate(exemplars):
        excerpt = ex[:800]
        if len(ex) > 800:
            excerpt = excerpt.rsplit(" ", 1)[0] + " [...]"
        truncated.append(f"--- Voice Example {i + 1} ---\n{excerpt}")
    return f"{header}\n" + "\n\n".join(truncated)


_PLATFORM_INSTRUCTIONS = """\
== PLATFORM: LINKEDIN POST ==

Write a LinkedIn post of 300 to 600 words on this topic.

STRUCTURE:
- Opening hook (1-2 sentences): Grab attention with a surprising fact, a \
contrarian take, or a concrete observation. The first line shows in the feed \
preview before "see more," so it must earn the click.
- Body (3 insight paragraphs): Each paragraph advances one idea. Use short \
paragraphs (2-4 sentences). LinkedIn readers scan; dense blocks get skipped. \
Weave in real experience, specific examples, or data points.
- Closing thought (1-2 sentences): Land the point. This can be a question \
that invites genuine discussion (not engagement bait), a forward-looking \
statement, or a sharp summary.

VOICE ON LINKEDIN:
- Write like a smart person talking to other smart people at a conference \
hallway conversation. Not a keynote. Not a TED talk. A hallway.
- Honest takes on building, decentralization, tech industry dynamics. Share \
real observations from real experience.
- Be opinionated. Hedging every sentence makes you invisible on LinkedIn.
- Humor is welcome but should serve the point, not perform for the audience.

BANNED ON LINKEDIN:
- "I'm humbled to announce" or any humility theater.
- "Agree?" as a one-word closing (pure engagement bait).
- Excessive emoji use. Zero to three total, and only if they add clarity.
- Line-break-per-sentence formatting (the "LinkedIn poem" format). Use \
actual paragraphs.
- Hustle-porn: "I woke up at 4am and..." / "Here's what failing taught me."
- Corporate glaze: "Excited to share" / "Thrilled to announce" / "Proud of \
this team."
- Cringe inspiration: feel-good platitudes disguised as insight.
- Hashtag walls at the end. Three hashtags max, and only relevant ones.

OUTPUT FORMAT:
Return the post as plain text. No title or metadata. Just the post body, \
ready to paste into LinkedIn's compose box.

If you include hashtags, place them naturally at the end on their own line."""
