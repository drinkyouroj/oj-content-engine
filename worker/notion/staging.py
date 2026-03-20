"""Notion staging — write content drafts to Notion for review.

Creates one Notion page per ContentDraft in the Second Brain database.
Properties include score breakdown, platform, model used, thesis status.
Page body contains the generated content.

Implements PRD Section 6 (Notion Staging).

Inputs:
    - AsyncSession connected to Postgres
    - Configured NotionClient instance

Outputs:
    - Notion page IDs stored back on ContentDraft rows
    - SystemAlert rows on failure
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from worker.app.models.content_draft import ContentDraft
from worker.app.models.scored_signal import ScoredSignal
from worker.app.models.system_alert import SystemAlert
from worker.app.models.topic import Topic
from worker.notion.client import NotionClient, NotionWriteError

logger = logging.getLogger(__name__)


async def stage_drafts(
    session: AsyncSession,
    client: NotionClient,
) -> dict[str, int]:
    """Stage all unstaged content drafts in Notion.

    Queries ContentDrafts where notion_page_id is null, creates Notion pages,
    stores page IDs back on the draft rows. Continues on per-draft failure,
    recording a SystemAlert for each failure so ops can investigate without
    losing the rest of the batch.

    Implements PRD Section 6 (Notion Staging).

    Estimated runtime: N * ~2 s per draft (Notion HTTPS round-trip + rate-limit
    sleep). For typical batches of 4–16 drafts this is 8–32 s.
    Retry behaviour: no internal retries per draft — ARQ job owns retry at the
    batch level. Per-draft failures are isolated and do not abort the batch.
    Failure mode: NotionWriteError is caught, a SystemAlert is created, and the
    loop continues.

    Args:
        session: Async database session.
        client: Configured NotionClient instance.

    Returns:
        Dictionary with counts: {"staged": N, "errors": N}.
    """
    # Eagerly load topic → scored_signal → signal to avoid N+1 queries when
    # reading score breakdown and signal title inside the loop.
    stmt = (
        select(ContentDraft)
        .where(
            ContentDraft.notion_page_id == None,  # noqa: E711
        )
        .options(
            selectinload(ContentDraft.topic)
            .selectinload(Topic.scored_signal)
            .selectinload(ScoredSignal.signal),
        )
    )
    result = await session.execute(stmt)
    drafts = result.scalars().all()

    counts = {"staged": 0, "errors": 0}

    for draft in drafts:
        # Cache identifiers before any DB ops that might expire the object
        draft_id = draft.id
        try:
            topic = draft.topic
            composite_score = 0.0
            score_breakdown = ""

            if topic and topic.scored_signal:
                composite_score = float(topic.scored_signal.composite_score)
                breakdown = topic.scored_signal.score_breakdown or {}
                score_breakdown = json.dumps(breakdown, indent=2)

            signal_title = "Unknown"
            if topic and topic.scored_signal and topic.scored_signal.signal:
                signal_title = topic.scored_signal.signal.title

            # Normalise platform to a plain string regardless of whether it's
            # an enum instance or already a string.
            platform_name = (
                draft.platform.value
                if hasattr(draft.platform, "value")
                else str(draft.platform)
            )
            title = f"[{platform_name.capitalize()}] {signal_title}"

            page_id = await client.create_page(
                title=title,
                platform=platform_name,
                content=draft.content,
                properties={
                    "composite_score": composite_score,
                    "thesis_provided": topic.thesis_provided if topic else False,
                    "model_used": draft.model_used or "unknown",
                    "token_cost": float(draft.token_cost) if draft.token_cost else 0.0,
                    "topic_id": str(topic.id) if topic else "",
                    "score_breakdown": score_breakdown,
                },
            )

            # Attach generation metadata as a comment (non-fatal if permissions missing)
            try:
                metadata = {
                    "model": draft.model_used,
                    "generated_at": (
                        draft.generated_at.isoformat() if draft.generated_at else None
                    ),
                    "generation_metadata": draft.generation_metadata,
                }
                await client.add_comment(page_id, json.dumps(metadata, indent=2))
            except NotionWriteError:
                logger.warning(
                    "Could not add comment to page %s (check integration permissions)",
                    page_id,
                )

            # Bidirectional link: store Notion page ID on the draft row so the
            # approval UI can deep-link directly to the Notion page.
            draft.notion_page_id = page_id
            counts["staged"] += 1

            logger.info("Staged draft %s → Notion page %s", draft_id, page_id)

        except (NotionWriteError, Exception) as exc:
            logger.error("Failed to stage draft %s: %s", draft_id, exc)
            alert = SystemAlert(
                source="notion",
                alert_type="notion_write_failed",
                last_failure_at=datetime.now(timezone.utc),
            )
            session.add(alert)
            counts["errors"] += 1

    return counts
