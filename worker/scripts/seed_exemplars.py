"""Seed voice exemplars from published Substack articles.

Fetches HTML from Substack, extracts article body text using BeautifulSoup,
detects the content vertical, and inserts rows into voice_exemplars.

Implements PRD Section 4 (Voice Injection Points) — exemplar seeding step.

Inputs:
    EXEMPLAR_URLS list below (hardcoded set of drinkYourOJ Substack posts).
    DATABASE_URL environment variable via worker.app.config.

Outputs:
    VoiceExemplar rows in Postgres (platform="substack", active=True).
    Skips any URL whose content is already present (dedup by URL in content).

Estimated runtime: ~30 seconds (7 HTTP fetches + 7 DB inserts).
Retry behavior: httpx raises on HTTP errors; script logs and continues per URL.
Failure mode: Individual URL failures are logged and skipped; script exits 0
    if at least one exemplar is inserted.

Run as:
    cd worker && python3.12 -m worker.scripts.seed_exemplars
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory
from worker.app.models.content_draft import Platform
from worker.app.models.voice_exemplar import VoiceExemplar
from worker.generation.verticals import detect_vertical

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Target Substack URLs
# ---------------------------------------------------------------------------

EXEMPLAR_URLS: list[str] = [
    "https://drinkyouroj.substack.com/p/schneider-solved-the-salary-cap-while-everyone-else-complained",
    "https://drinkyouroj.substack.com/p/13-3-the-box-score-that-ended-the-can-seattles-defense-travel-debate",
    "https://drinkyouroj.substack.com/p/disguise-and-destroy-the-macdonald-method-that-broke-nfl-offenses",
    "https://drinkyouroj.substack.com/p/trump-is-covering-up-the-minneapolis-ice-shooting-just-like-hes-covering-up-epstein",
    "https://drinkyouroj.substack.com/p/nodes-over-numbers",
    "https://drinkyouroj.substack.com/p/the-false-balance-trap",
    "https://drinkyouroj.substack.com/p/my-autism-self-assessment-scores",
]


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------


def extract_article_text(html: str, url: str) -> tuple[str, str]:
    """Extract title and body text from a Substack article HTML page.

    Tries selectors in priority order: .body.markup, .post-content, article.
    Falls back to the full <body> text if none match.

    Args:
        html: Raw HTML string from the HTTP response.
        url: Source URL (used only for logging context).

    Returns:
        Tuple of (title, body_text). Title may be empty string if not found.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = ""
    title_tag = soup.find("h1", class_="post-title") or soup.find("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Extract body using known Substack selectors, in priority order
    body_el = (
        soup.find(class_="body markup")
        or soup.find(class_="post-content")
        or soup.find("article")
        or soup.find("body")
    )

    if body_el:
        # Remove script, style, and nav noise
        for tag in body_el.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body_text = body_el.get_text(separator="\n", strip=True)
    else:
        body_text = soup.get_text(separator="\n", strip=True)

    return title, body_text


# ---------------------------------------------------------------------------
# Main seeding logic
# ---------------------------------------------------------------------------


async def seed_exemplars() -> None:
    """Fetch, parse, and insert Substack exemplars into voice_exemplars.

    For each URL in EXEMPLAR_URLS:
    1. Checks if this URL is already represented (by URL substring in content).
    2. Fetches the HTML with httpx (10s timeout).
    3. Parses title and body with BeautifulSoup.
    4. Detects the content vertical from title + body.
    5. Inserts a VoiceExemplar row if not already present.

    Raises:
        SystemExit(1): If DATABASE_URL is not set.
    """
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    inserted = 0
    skipped = 0
    errors = 0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10.0) as http:
        for url in EXEMPLAR_URLS:
            logger.info("Processing: %s", url)

            async with session_factory() as session:
                # Dedup check: look for the URL slug in existing exemplar content
                url_slug = url.split("/p/")[-1]
                result = await session.execute(
                    select(VoiceExemplar).where(
                        VoiceExemplar.content.contains(url_slug)
                    )
                )
                existing = result.scalars().first()
                if existing:
                    logger.info("  Skipping (already seeded): %s", url_slug)
                    skipped += 1
                    continue

                # Fetch HTML
                try:
                    response = await http.get(url)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.error("  HTTP error fetching %s: %s", url, exc)
                    errors += 1
                    continue

                # Extract content
                title, body = extract_article_text(response.text, url)

                if not body:
                    logger.warning("  No body text extracted from %s", url)
                    errors += 1
                    continue

                # Detect vertical
                vertical = detect_vertical(title, body)
                logger.info("  Detected vertical: %s (title=%r)", vertical, title[:60])

                # Build content string with URL header for future dedup checks
                content = f"[SOURCE: {url}]\n\n# {title}\n\n{body}"

                # Insert exemplar
                exemplar = VoiceExemplar(
                    content=content,
                    platform=Platform.SUBSTACK,
                    active=True,
                    vertical=vertical,
                )
                session.add(exemplar)
                await session.commit()
                logger.info("  Inserted exemplar id=%s vertical=%s", exemplar.id, vertical)
                inserted += 1

    await engine.dispose()

    print(f"\nDone. Inserted: {inserted}  Skipped: {skipped}  Errors: {errors}")
    if inserted == 0 and errors > 0:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Configure logging and run the async seeding coroutine."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(seed_exemplars())


if __name__ == "__main__":
    main()
