"""Substack long-form article prompt template.

Implements PRD Section 5 (Content Generation) for the Substack platform.
Supports four article templates that the LLM selects from based on topic
fit: Triple Connection, System Audit, Concept Decoder, and Pattern Report.

Exports:
    build_prompt(topic_title, topic_body, score_breakdown, thesis, exemplars) -> str
"""
from __future__ import annotations

from worker.generation.prompts._shared import format_source_urls, format_topic_context


def build_prompt(
    topic_title: str,
    topic_body: str,
    score_breakdown: dict[str, int],
    thesis: str | None,
    exemplars: list[str],
    source_urls: list[str] | None = None,
) -> str:
    """Assemble a Substack article generation prompt.

    Combines topic context, source URLs for citation, optional thesis,
    optional voice exemplars, and platform-specific structural instructions.

    Args:
        topic_title: Title of the triaged topic.
        topic_body: Body preview or summary of the topic.
        score_breakdown: Dict mapping rubric dimensions to integer scores (0-100).
        thesis: Human-supplied thesis angle, or None for AI-originated content.
        exemplars: List of exemplar content strings for voice calibration.
        source_urls: Real URLs to use for citations. Only these may be cited.

    Returns:
        Formatted prompt string ready to pass as the user message.
    """
    sections: list[str] = []

    sections.append(format_topic_context(topic_title, topic_body, score_breakdown))

    if source_urls:
        sections.append(format_source_urls(source_urls))

    sections.append(_format_thesis(thesis))

    if exemplars:
        sections.append(_format_exemplars(exemplars))

    sections.append(_PLATFORM_INSTRUCTIONS)

    return "\n\n".join(sections)


def _format_thesis(thesis: str | None) -> str:
    if thesis:
        return f"== THESIS ==\n\nBuild the article around this angle:\n{thesis}"
    return (
        "== THESIS ==\n\n"
        "No thesis provided. This is AI-originated content that will need "
        "heavy editing. Generate your best angle based on the topic and score "
        "breakdown, but flag clearly at the top of your output that this is "
        "an AI-generated angle, not a human editorial direction."
    )


def _format_exemplars(exemplars: list[str]) -> str:
    header = (
        "== VOICE REFERENCE EXAMPLES ==\n\n"
        "These examples demonstrate the writing STYLE and VOICE you must use. "
        "They are NOT about the topic you are writing about. Ignore their subject "
        "matter entirely. Only study: sentence rhythm, humor style, metaphor usage, "
        "how the author opens sections, how abstract ideas get concrete examples, "
        "and the overall tone (dry, direct, systems-thinking, occasionally funny).\n\n"
        "DO NOT write about the subjects in these examples. Write about the TOPIC above.\n"
    )
    # Truncate each exemplar to ~1500 chars to prevent topic bleed
    truncated = []
    for i, ex in enumerate(exemplars):
        excerpt = ex[:1500]
        if len(ex) > 1500:
            excerpt = excerpt.rsplit(" ", 1)[0] + " [...]"
        truncated.append(f"--- Voice Example {i + 1} ---\n{excerpt}")
    return f"{header}\n" + "\n\n".join(truncated)


_PLATFORM_INSTRUCTIONS = """\
== PLATFORM: SUBSTACK LONG-FORM ARTICLE ==

Choose the article template that best fits this topic. You have four options:

TEMPLATE 1 - TRIPLE CONNECTION
Structure: The Spark (~400 words) > The Pattern (~500 words) > \
The Protocol (~400 words) > Personal Code (~200-300 words)
Best for: topics where you can connect a surprising observation to a broader \
pattern and then to a concrete system or protocol.

TEMPLATE 2 - SYSTEM AUDIT
Structure: The Glitch (~400 words) > The Source Code (~500 words) > \
The Upgrade (~400 words) > My Debug (~200-300 words)
Best for: topics where something is broken and you want to diagnose why, \
then propose a fix. Investigative or critical angle.

TEMPLATE 3 - CONCEPT DECODER
Structure: The Definition (~300 words) > The Mechanics (~600 words) > \
The Applications (~400 words) > The Human Element (~200-300 words)
Best for: explaining a concept that is widely misunderstood or oversimplified. \
Educational angle with opinion woven in.

TEMPLATE 4 - PATTERN REPORT (LISTICLE)
Structure: Intro (~200-250 words) > 7-10 Pattern Items (~100-150 words each) \
> The Meta-Pattern (~200-250 words)
Best for: trend roundups, pattern collections, or "things I noticed" pieces. \
Each item must have a distinct insight, not just a description.

HARD CONSTRAINTS:
- Total word count: 1,500-1,600 words. Absolute ceiling: 1,700. Do not exceed.
- Title: 60 characters max. Must make a claim or challenge an assumption. \
No colons. No "How to." No question marks.
- Subtitle: 150 characters max. Clarifies the angle or adds a hook.
- Include 3-4 image markers placed at natural section breaks. Each marker must \
contain:
  * A Flux/Midjourney image generation prompt (50-80 words). Describe the \
visual concept, style, mood, color palette. Be specific enough for AI image \
generation.
  * Alt text (1 sentence describing what the image shows for accessibility).
  * A punchy 1-sentence caption.
  Format each image marker like this:
  [IMAGE: <generation prompt>]
  [ALT: <alt text>]
  [CAPTION: <caption>]
- End the piece with either a thought-provoking question OR a clear declarative \
point. Not both. Pick the one that lands harder.

SOURCES AND FOOTNOTES (MANDATORY):
- Every statistic, data point, or factual claim MUST have an inline footnote \
marker like [1], [2], [3] in the article body where the claim appears.
- The article MUST end with a SOURCES section listing every footnoted source \
with its full URL.
- ONLY cite sources whose URLs were provided to you in the TOPIC or SOURCE \
URLS sections above. Do NOT invent, guess, or hallucinate URLs. If you \
cannot attribute a claim to a provided source, either rephrase the claim as \
your own analysis (no footnote needed) or omit it. Never write [SOURCE NEEDED].
- Example inline usage: "Stablecoin volume hit $46 trillion annually.[1]"
- The SOURCES section is NOT optional. An article without sources is incomplete.

OUTPUT FORMAT:
Return the article as plain text with EXACTLY this structure:

TITLE: <title text, 60 chars max>
SUBTITLE: <subtitle text, 150 chars max>
TEMPLATE: <template name>

<article body with [IMAGE] markers and inline footnote markers like [1], [2]>

SOURCES:
[1] Description — https://example.com/source-url
[2] Description — https://example.com/another-source
[3] Description — https://example.com/third-source"""
