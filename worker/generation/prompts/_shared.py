"""Shared formatting utilities for prompt assembly.

Used by all platform prompt modules to ensure consistent formatting of
topic context, thesis injection, exemplar presentation, and source article
injection for social platform generation.
"""
from __future__ import annotations


def format_topic_context(
    topic_title: str,
    topic_body: str,
    score_breakdown: dict[str, int],
) -> str:
    """Format topic metadata and rubric scores into a prompt section.

    Args:
        topic_title: Title of the triaged topic.
        topic_body: Body preview or summary text.
        score_breakdown: Dict mapping rubric dimension names to integer scores.

    Returns:
        Formatted string containing topic context for prompt injection.
    """
    score_lines = "\n".join(
        f"  {dim.replace('_', ' ').title()}: {score}/100"
        for dim, score in score_breakdown.items()
    )
    return (
        f"== TOPIC ==\n\n"
        f"Title: {topic_title}\n"
        f"Body: {topic_body}\n\n"
        f"Rubric Scores:\n{score_lines}"
    )


def format_source_article(substack_content: str) -> str:
    """Format the Substack article as a source context section for social prompts.

    Social content is derived from the Substack article. This section gives the
    LLM the full long-form piece to distill into platform-appropriate content.

    Args:
        substack_content: The full generated Substack article text.

    Returns:
        Formatted string containing the source article for prompt injection.
    """
    return (
        "== SOURCE ARTICLE (SUBSTACK) ==\n\n"
        "The following is the full Substack article already written on this topic. "
        "Your job is to distill and adapt it for the target platform. Do NOT "
        "simply summarize or restate. Extract the sharpest angles, most "
        "surprising insights, and strongest arguments, then reformat them "
        "for the platform's constraints and audience expectations.\n\n"
        f"{substack_content}"
    )
