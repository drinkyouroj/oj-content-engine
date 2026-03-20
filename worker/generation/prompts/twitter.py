"""Twitter/X thread prompt template.

Implements PRD Section 5 (Content Generation) for the Twitter/X platform.
Generates threads of 5-12 tweets with a scroll-stopping hook and a closing CTA.

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
    """Assemble a Twitter/X thread generation prompt.

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
        return f"== THESIS ==\n\nBuild the thread around this angle:\n{thesis}"
    return (
        "== THESIS ==\n\n"
        "No thesis provided. This is AI-originated content that will need "
        "heavy editing. Generate your sharpest angle based on the topic, "
        "but note in your output that no human editorial direction was given."
    )


def _format_exemplars(exemplars: list[str]) -> str:
    header = (
        "== VOICE REFERENCE EXAMPLES ==\n\n"
        "These examples show the writing STYLE only. Ignore their subject matter. "
        "Study tone, rhythm, directness, and humor. Twitter voice is punchier "
        "and more compressed than long-form, but the personality is the same.\n\n"
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
== PLATFORM: TWITTER/X THREAD ==

Write a thread of 5 to 12 tweets on this topic.

TWEET RULES:
- Every single tweet must be 280 characters or fewer. No exceptions.
- Tweet 1 is the hook. It must stop the scroll. Lead with the most surprising, \
counterintuitive, or provocative framing of the topic. No preamble.
- Tweets 2 through N-1 are the substance. Each tweet should contain one \
thought, one insight, one beat. This is a thread of *thoughts*, not a \
bulleted list reformatted with line breaks.
- The final tweet is the call to action. Drive to Substack, ask a question, \
or land a closing punch. Make it feel like a destination, not a fade-out.

BANNED PATTERNS:
- "1/ Let me tell you about X" or any generic "1/ Here's why" opener.
- Numbering tweets (no "1/", "2/", etc.). The thread format handles sequencing.
- Thread-of-bullet-points: each tweet that reads like a bullet item is a failure. \
Every tweet should feel like it could stand alone as a post.
- Empty filler tweets ("Let me explain." / "Here's the thing." / "Stay with me.")
- Hashtag spam. Zero to one hashtag per tweet max, and only if it genuinely \
adds discoverability.

VOICE CALIBRATION:
- Punchy. Opinionated. Occasionally funny.
- Compression is the skill here. Say more with fewer words.
- If a tweet needs a setup and a punchline, the setup should be one sentence max.
- Contrarian framing works well for hooks, but the substance tweets must earn \
the contrarian claim with real reasoning.

OUTPUT FORMAT:
Return each tweet on its own line, separated by a blank line. Prefix each with \
[TWEET]:

[TWEET] <tweet 1 text>

[TWEET] <tweet 2 text>

...

[TWEET] <final tweet text>"""
