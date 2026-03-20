"""ARQ job for Notion staging.

Stages content drafts in Notion for Justin's review.
Creates Notion pages with properties and metadata comments.

Implements PRD Section 6 (Notion Staging Schema).
"""
from __future__ import annotations

import logging

from worker.app.config import get_settings
from worker.app.database import make_engine, make_session_factory
from worker.notion.staging import stage_drafts
from worker.notion.client import NotionClient

logger = logging.getLogger(__name__)


async def run_notion_staging_job(ctx: dict) -> dict[str, int]:
    """ARQ job: stage unstaged content drafts in Notion.

    Queries ContentDrafts where notion_page_id is null and creates
    Notion pages with rate-limited batching.

    Args:
        ctx: ARQ job context dictionary.

    Returns:
        Dictionary with counts: {"staged": N, "errors": N}.

    Estimated runtime: ~1s per draft (2 API calls x 400ms delay).
    Retry behavior: ARQ default (3 retries with backoff).
    Failure mode: Per-draft errors logged as system_alerts.
    """
    settings = get_settings()

    if not settings.notion_api_key or not settings.notion_db_id:
        logger.warning("Notion API key or DB ID not configured — skipping staging")
        return {"staged": 0, "errors": 0}

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    session = session_factory()

    try:
        client = NotionClient(
            api_key=settings.notion_api_key,
            database_id=settings.notion_db_id,
        )
        await client.setup_database()
        counts = await stage_drafts(session, client)
        await session.commit()
        logger.info("Notion staging complete: %s", counts)
        return counts
    finally:
        await session.close()
        await engine.dispose()
