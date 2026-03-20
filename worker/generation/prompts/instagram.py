"""Instagram caption + image card prompt template.

Implements PRD Section 5 (Content Generation) for the Instagram platform.
Generates a concise caption (150 words max) paired with a Flux/Midjourney
prompt for a conceptual image card. The visual carries the weight; the
caption adds context without repeating the image content.

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
    """Assemble an Instagram caption + image card generation prompt.

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
        "heavy editing. Generate a visually compelling angle, but note "
        "that no human editorial direction was given."
    )


def _format_exemplars(exemplars: list[str]) -> str:
    header = (
        "== VOICE REFERENCE EXAMPLES ==\n\n"
        "These examples show the writing STYLE only. Ignore their subject matter. "
        "Study tone and compression. Instagram voice is the most compressed "
        "version of the brand: punchy, visual-first, every word earns its spot.\n\n"
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
== PLATFORM: INSTAGRAM CAPTION + IMAGE CARD ==

Create an Instagram post consisting of a caption and an image card prompt.

CAPTION RULES:
- 150 words maximum. Shorter is better.
- The caption adds context the image cannot convey. Do not describe what the \
image shows. Instead, provide the opinion, the context, or the "so what."
- Front-load the hook. Instagram truncates after ~125 characters in the feed. \
The first sentence must work on its own.
- End with a question or a sharp closing line. Not both.
- Hashtags: 5-10 relevant hashtags on a separate final line. Mix niche and \
broad. No banned-word hashtags.

IMAGE CARD RULES:
- The image card is a conceptual visual, not a photograph of a person. Think: \
diagrams, data visualizations, quote cards, abstract illustrations, isometric \
technical art, infographic snippets.
- The visual should carry the core idea. Someone scrolling should get the point \
from the image alone before reading the caption.
- No selfie-with-text-overlay format.
- No generic stock imagery (handshakes, lightbulbs, gears).
- No walls of text on the image. If it is a quote card, keep it to 15 words max.

Brand visual guidelines:
- Color palette: teal (#00B4D8) and orange (#FF6B35) as accents on dark or \
neutral backgrounds.
- Style: clean, modern, slightly technical. Think Bloomberg Terminal meets \
Figma. Data-informed aesthetic.
- Typography on cards: sans-serif, high contrast, minimal.

OUTPUT FORMAT:
Return the output in exactly this structure:

CAPTION:
<caption text>

<hashtag line>

---IMAGE CARD---

CONCEPT: <1 sentence describing the visual concept>
PROMPT: <Flux/Midjourney image generation prompt, 50-80 words. Specify style, \
mood, color palette, composition, and key visual elements.>
ALT: <1 sentence alt text for accessibility>"""
