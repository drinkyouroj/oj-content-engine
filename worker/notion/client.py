"""
Notion API client wrapper with rate limiting.

Wraps the `notion-client` Python SDK to provide async-safe page and comment
creation for staging generated content drafts in the review database.

Implements PRD Section 6 (Notion Staging). Every API call is rate-limited to
400 ms delay (Notion enforces ~3 req/s). All SDK calls are dispatched via
`asyncio.to_thread()` because `notion_client.Client` is synchronous.

Inputs:
    - NOTION_API_KEY and NOTION_DB_ID from environment (loaded by caller)
    - Structured content metadata (title, platform, scores, etc.)

Outputs:
    - Notion page ID (str) on successful page creation
    - Side-effect: optional comment pinned to the page

Raises:
    NotionWriteError: on any Notion API failure after the SDK call completes
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from notion_client import Client

logger = logging.getLogger(__name__)

# Notion enforces ~3 req/s; 400 ms between calls keeps us safely under the cap.
_RATE_LIMIT_DELAY = 0.4

# Notion rich-text blocks have a hard 2 000-character content limit.
_BLOCK_CHAR_LIMIT = 2_000


class NotionWriteError(Exception):
    """Raised when a Notion API write fails."""


def _split_content(content: str, chunk_size: int) -> list[str]:
    """
    Split a long string into chunks no larger than `chunk_size` characters.

    Notion paragraph blocks are capped at 2 000 characters. This helper ensures
    content that exceeds that limit is distributed across multiple blocks rather
    than being truncated or raising an API error.

    Args:
        content: Full text string to split.
        chunk_size: Maximum characters per chunk.

    Returns:
        List of strings, each at most `chunk_size` characters long.
    """
    if not content:
        return [""]
    return [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]


class NotionClient:
    """
    Async wrapper around the synchronous `notion_client.Client`.

    All Notion SDK calls are run in a thread pool via `asyncio.to_thread()` so
    they do not block the ARQ event loop. A fixed 400 ms delay is applied after
    every API call to respect Notion's rate limit.

    Implements PRD Section 6 — Notion Staging.
    """

    def __init__(self, api_key: str, database_id: str) -> None:
        """
        Initialise the Notion client.

        Args:
            api_key: Notion integration token (``secret_...``).
            database_id: UUID of the target Notion database.

        Raises:
            ValueError: If either argument is empty/falsy.
        """
        if not api_key:
            raise ValueError("Notion api_key is required")
        if not database_id:
            raise ValueError("Notion database_id is required")

        self._database_id = database_id
        self._client = Client(auth=api_key)

    async def setup_database(self) -> None:
        """Ensure the target database has all required properties.

        Creates any missing properties on the Notion database via the
        databases.update API. Safe to call multiple times — Notion ignores
        properties that already exist.

        Should be called once before the first staging run.
        """
        properties = {
            "Platform": {"select": {"options": [
                {"name": "Substack"}, {"name": "Twitter"},
                {"name": "Linkedin"}, {"name": "Instagram"},
            ]}},
            "Status": {"select": {"options": [
                {"name": "Draft"}, {"name": "Review"},
                {"name": "Approved"}, {"name": "Published"}, {"name": "Killed"},
            ]}},
            "Composite Score": {"number": {}},
            "Score Breakdown": {"rich_text": {}},
            "Generated At": {"date": {}},
            "Topic ID": {"rich_text": {}},
            "Thesis Provided": {"checkbox": {}},
            "Model Used": {"rich_text": {}},
            "Token Cost": {"number": {}},
        }

        try:
            await asyncio.to_thread(
                self._client.databases.update,
                database_id=self._database_id,
                properties=properties,
            )
            logger.info("Database properties ensured for %s", self._database_id)
        except Exception as exc:
            logger.error("Failed to update database properties: %s", exc)
            raise NotionWriteError(f"Failed to setup database: {exc}") from exc
        finally:
            await asyncio.sleep(_RATE_LIMIT_DELAY)

    async def create_page(
        self,
        title: str,
        platform: str,
        content: str,
        properties: dict,
    ) -> str:
        """
        Create a draft page in the Notion staging database.

        Constructs the full Notion page payload from the provided metadata and
        content string, then creates the page via the SDK. Content longer than
        2 000 characters is automatically split across multiple paragraph blocks.

        Implements PRD Section 6.2 (Page Schema).

        Estimated runtime: <2 s (single HTTPS round-trip + 400 ms sleep).
        Retry behaviour: no internal retries — caller (ARQ job) owns retry logic.
        Failure mode: raises `NotionWriteError` wrapping the original exception.

        Args:
            title: Page title displayed in the Notion database view.
            platform: Target platform slug (e.g. ``"twitter"``, ``"substack"``).
            content: Full generated content body for the page.
            properties: Dict of generation metadata. Expected keys:
                - ``composite_score`` (float): Overall triage score.
                - ``score_breakdown`` (str): Human-readable per-dimension scores.
                - ``generated_at`` (str): ISO-8601 datetime string.
                - ``topic_id`` (int | str): Source topic identifier.
                - ``thesis_provided`` (bool): Whether a custom thesis was supplied.
                - ``model_used`` (str): LLM model identifier.
                - ``token_cost`` (float): Estimated token cost in USD.

        Returns:
            Notion page ID (UUID string) of the newly created page.

        Raises:
            NotionWriteError: If the Notion API call fails for any reason.
        """
        composite_score: float = properties.get("composite_score", 0.0)
        score_breakdown: str = properties.get("score_breakdown", "")
        generated_at: str = properties.get(
            "generated_at",
            datetime.now(timezone.utc).isoformat(),
        )
        topic_id = properties.get("topic_id", "")
        thesis_provided: bool = bool(properties.get("thesis_provided", False))
        model_used: str = properties.get("model_used", "")
        token_cost: float = properties.get("token_cost", 0.0)

        notion_properties = {
            "Title": {"title": [{"text": {"content": title}}]},
            "Platform": {"select": {"name": platform.capitalize()}},
            "Status": {"select": {"name": "Draft"}},
            "Composite Score": {"number": composite_score},
            "Score Breakdown": {
                "rich_text": [{"text": {"content": score_breakdown}}]
            },
            "Generated At": {"date": {"start": generated_at}},
            "Topic ID": {
                "rich_text": [{"text": {"content": str(topic_id)}}]
            },
            "Thesis Provided": {"checkbox": thesis_provided},
            "Model Used": {
                "rich_text": [{"text": {"content": model_used}}]
            },
            "Token Cost": {"number": token_cost},
        }

        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": chunk}}
                    ]
                },
            }
            for chunk in _split_content(content, _BLOCK_CHAR_LIMIT)
        ]

        try:
            page = await asyncio.to_thread(
                self._client.pages.create,
                parent={"database_id": self._database_id},
                properties=notion_properties,
                children=children,
            )
        except Exception as exc:
            logger.error("Notion page creation failed: %s", exc)
            raise NotionWriteError(f"Failed to create Notion page: {exc}") from exc
        finally:
            await asyncio.sleep(_RATE_LIMIT_DELAY)

        page_id: str = page["id"]
        logger.info("Created Notion page %s for platform=%s", page_id, platform)
        return page_id

    async def add_comment(self, page_id: str, comment_text: str) -> None:
        """
        Add a comment to an existing Notion page.

        Used to attach generation metadata or reviewer notes to a staged draft
        without altering the page body.

        Estimated runtime: <2 s (single HTTPS round-trip + 400 ms sleep).
        Retry behaviour: no internal retries — caller owns retry logic.
        Failure mode: raises `NotionWriteError` wrapping the original exception.

        Args:
            page_id: UUID of the target Notion page.
            comment_text: Plain-text body of the comment.

        Raises:
            NotionWriteError: If the Notion API call fails for any reason.
        """
        try:
            await asyncio.to_thread(
                self._client.comments.create,
                parent={"page_id": page_id},
                rich_text=[{"type": "text", "text": {"content": comment_text}}],
            )
        except Exception as exc:
            logger.error("Notion comment creation failed: %s", exc)
            raise NotionWriteError(
                f"Failed to add comment to page {page_id}: {exc}"
            ) from exc
        finally:
            await asyncio.sleep(_RATE_LIMIT_DELAY)

        logger.info("Added comment to Notion page %s", page_id)
