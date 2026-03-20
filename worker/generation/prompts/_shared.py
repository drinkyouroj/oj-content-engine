"""Shared formatting utilities for prompt assembly.

Used by all platform prompt modules to ensure consistent formatting of
topic context, thesis injection, and exemplar presentation.
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
