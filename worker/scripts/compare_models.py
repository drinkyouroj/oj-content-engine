"""Model quality comparison script: Groq vs Anthropic.

Loads a topic from the database by UUID, generates a Substack draft using
both Groq (llama-3.3-70b-versatile) and Anthropic (claude-sonnet-4-5), and
prints a side-by-side summary. Full outputs are saved to:
    output/comparisons/<topic-id>/groq.md
    output/comparisons/<topic-id>/anthropic.md

Implements tooling for PRD Section 4 quality assurance.

Inputs:
    - Topic UUID as positional CLI argument.
    - DATABASE_URL, GROQ_API_KEY, ANTHROPIC_API_KEY environment variables.

Outputs:
    - Printed comparison table to stdout.
    - Markdown files in output/comparisons/<topic-id>/.

Estimated runtime: 30-60 seconds (two LLM calls with retries).
Retry behavior: inherits LLMClient retry (3 attempts, exponential backoff).
Failure mode: prints error and exits 1 if topic not found or both calls fail.

Run as:
    cd worker && python3.12 -m worker.scripts.compare_models <topic-uuid>
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory
from worker.app.models.topic import Topic
from worker.generation.exemplar_selector import select_exemplars
from worker.generation.llm_client import LLMClient, LLMGenerationError, LLMResponse
from worker.generation.prompts.substack import build_prompt as build_substack_prompt
from worker.generation.prompts.system import build_system_prompt
from worker.generation.verticals import detect_vertical

logger = logging.getLogger(__name__)

# Hardcoded provider/model pairs for comparison
_GROQ_PROVIDER = "groq"
_GROQ_MODEL = "llama-3.3-70b-versatile"
_ANTHROPIC_PROVIDER = "anthropic"
_ANTHROPIC_MODEL = "claude-sonnet-4-5"

# Output root relative to repo root
_OUTPUT_ROOT = Path(__file__).parent.parent.parent / "output" / "comparisons"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _word_count(text: str) -> int:
    """Return the approximate word count of a string."""
    return len(text.split())


def _print_comparison(
    topic_title: str,
    groq_result: LLMResponse | Exception,
    anthropic_result: LLMResponse | Exception,
) -> None:
    """Print a formatted side-by-side comparison to stdout.

    Args:
        topic_title: Title of the topic being compared.
        groq_result: LLMResponse from Groq or an Exception if generation failed.
        anthropic_result: LLMResponse from Anthropic or an Exception if generation failed.
    """
    print("\n" + "=" * 72)
    print(f"MODEL COMPARISON — {topic_title[:60]}")
    print("=" * 72)

    headers = ["Metric", "Groq (llama-3.3-70b)", "Anthropic (claude-sonnet-4-5)"]
    col_w = [20, 24, 26]

    def row(label: str, groq_val: str, ant_val: str) -> None:
        print(f"  {label:<{col_w[0]}} {groq_val:<{col_w[1]}} {ant_val:<{col_w[2]}}")

    print()
    row(*headers)
    print("  " + "-" * (sum(col_w) + 4))

    for label, gr, an in _build_comparison_rows(groq_result, anthropic_result):
        row(label, gr, an)

    print()
    print("First 200 chars:")
    print()
    print("  GROQ:")
    if isinstance(groq_result, LLMResponse):
        print(f"    {groq_result.content[:200]!r}")
    else:
        print(f"    ERROR: {groq_result}")

    print()
    print("  ANTHROPIC:")
    if isinstance(anthropic_result, LLMResponse):
        print(f"    {anthropic_result.content[:200]!r}")
    else:
        print(f"    ERROR: {anthropic_result}")

    print()


def _build_comparison_rows(
    groq_result: LLMResponse | Exception,
    anthropic_result: LLMResponse | Exception,
) -> list[tuple[str, str, str]]:
    """Build metric rows for the comparison table.

    Args:
        groq_result: Groq LLMResponse or Exception.
        anthropic_result: Anthropic LLMResponse or Exception.

    Returns:
        List of (label, groq_value, anthropic_value) string tuples.
    """
    def _fmt(result: LLMResponse | Exception, attr: str) -> str:
        if isinstance(result, Exception):
            return f"ERROR: {str(result)[:20]}"
        val = getattr(result, attr, None)
        if val is None:
            return "—"
        return str(val)

    def _wc(result: LLMResponse | Exception) -> str:
        if isinstance(result, LLMResponse):
            return str(_word_count(result.content))
        return "—"

    return [
        ("Status", "OK" if isinstance(groq_result, LLMResponse) else "FAILED",
         "OK" if isinstance(anthropic_result, LLMResponse) else "FAILED"),
        ("Provider", _fmt(groq_result, "provider"), _fmt(anthropic_result, "provider")),
        ("Model", _fmt(groq_result, "model")[:24], _fmt(anthropic_result, "model")[:26]),
        ("Total tokens", _fmt(groq_result, "total_tokens"), _fmt(anthropic_result, "total_tokens")),
        ("Word count", _wc(groq_result), _wc(anthropic_result)),
    ]


def _save_output(topic_id: str, provider: str, result: LLMResponse | Exception) -> None:
    """Save a generation result to output/comparisons/<topic-id>/<provider>.md.

    Args:
        topic_id: Topic UUID string used as the subdirectory name.
        provider: Provider name ("groq" or "anthropic") used as the filename.
        result: LLMResponse to save, or Exception if generation failed.
    """
    out_dir = _OUTPUT_ROOT / topic_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{provider}.md"

    if isinstance(result, LLMResponse):
        content = (
            f"# {provider.upper()} — {result.model}\n\n"
            f"**Tokens:** {result.total_tokens}  \n"
            f"**Words:** {_word_count(result.content)}\n\n"
            "---\n\n"
            f"{result.content}"
        )
    else:
        content = f"# {provider.upper()} — FAILED\n\n```\n{result}\n```\n"

    out_path.write_text(content, encoding="utf-8")
    logger.info("Saved %s output to %s", provider, out_path)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Main async flow
# ---------------------------------------------------------------------------


async def compare(topic_id: str) -> None:
    """Load topic, generate with both providers, print comparison.

    Args:
        topic_id: UUID string of the target topic row.

    Raises:
        SystemExit(1): If the topic is not found or both generations fail.
    """
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    async with session_factory() as session:
        # Load topic with nested scored_signal -> signal
        result = await session.execute(
            select(Topic)
            .where(Topic.id == topic_id)
            .options(
                selectinload(Topic.scored_signal).selectinload(
                    __import__(
                        "worker.app.models.scored_signal",
                        fromlist=["ScoredSignal"],
                    ).ScoredSignal.signal
                )
            )
        )
        topic = result.scalars().first()

    if topic is None:
        print(f"ERROR: Topic {topic_id!r} not found in database.", file=sys.stderr)
        sys.exit(1)

    signal = topic.scored_signal.signal
    title = signal.title
    body = signal.body_preview or ""
    score_breakdown = topic.scored_signal.score_breakdown
    thesis = topic.thesis

    # Detect vertical and select exemplars
    vertical = detect_vertical(title, body)
    print(f"\nTopic: {title[:70]}")
    print(f"Vertical: {vertical}")
    print(f"Thesis: {'(provided)' if thesis else '(none — AI-originated)'}")

    async with session_factory() as session:
        exemplars = await select_exemplars(session, "substack", vertical)
    exemplar_texts = [e.content for e in exemplars]

    system_prompt = build_system_prompt()
    user_prompt = build_substack_prompt(
        topic_title=title,
        topic_body=body,
        score_breakdown=score_breakdown,
        thesis=thesis,
        exemplars=exemplar_texts,
    )

    # Build client with both keys
    client = LLMClient(
        groq_api_key=settings.groq_api_key,
        anthropic_api_key=settings.anthropic_api_key,
    )

    # Generate with Groq
    print("\nGenerating with Groq...")
    try:
        groq_result: LLMResponse | Exception = await client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=_GROQ_PROVIDER,
            model=_GROQ_MODEL,
        )
        print("  Groq: OK")
    except (LLMGenerationError, Exception) as exc:  # noqa: BLE001
        groq_result = exc
        print(f"  Groq: FAILED — {exc}")

    # Generate with Anthropic
    print("Generating with Anthropic...")
    try:
        anthropic_result: LLMResponse | Exception = await client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=_ANTHROPIC_PROVIDER,
            model=_ANTHROPIC_MODEL,
        )
        print("  Anthropic: OK")
    except (LLMGenerationError, Exception) as exc:  # noqa: BLE001
        anthropic_result = exc
        print(f"  Anthropic: FAILED — {exc}")

    # Print comparison
    _print_comparison(title, groq_result, anthropic_result)

    # Save outputs
    print("Saving outputs...")
    topic_id_str = str(topic.id)
    _save_output(topic_id_str, "groq", groq_result)
    _save_output(topic_id_str, "anthropic", anthropic_result)

    await engine.dispose()

    # Exit 1 if both failed
    if isinstance(groq_result, Exception) and isinstance(anthropic_result, Exception):
        print("\nBoth providers failed.", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI args and run the comparison coroutine.

    Usage:
        python3.12 -m worker.scripts.compare_models <topic-uuid>
    """
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if len(sys.argv) != 2:
        print("Usage: python3.12 -m worker.scripts.compare_models <topic-uuid>", file=sys.stderr)
        sys.exit(1)

    topic_id = sys.argv[1].strip()
    asyncio.run(compare(topic_id))


if __name__ == "__main__":
    main()
