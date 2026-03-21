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


def _content_to_blocks(content: str) -> list[dict]:
    """Convert article content into structured Notion blocks.

    Splits on paragraph boundaries (double newlines) and converts:
    - Lines starting with ## or # → heading blocks
    - Lines starting with [IMAGE:, [ALT:, [CAPTION: → callout blocks
    - Lines starting with TITLE:, SUBTITLE:, TEMPLATE:, SOURCES: → heading blocks
    - Everything else → paragraph blocks

    Long paragraphs (>2000 chars) are split into multiple paragraph blocks
    at sentence boundaries.

    Args:
        content: Full generated article text.

    Returns:
        List of Notion block dicts ready for the children parameter.
    """
    if not content:
        return [_paragraph_block("")]

    # Pre-process: split on newlines and re-group logically.
    # The LLM mixes \n and \n\n inconsistently, so we process line by line
    # and merge related lines (e.g. image marker groups).
    lines = content.split("\n")
    blocks: list[dict] = []
    current_paragraph: list[str] = []
    image_group: list[str] = []

    def flush_paragraph() -> None:
        text = " ".join(current_paragraph).strip()
        if text:
            for chunk in _split_text(text, _BLOCK_CHAR_LIMIT):
                blocks.append(_paragraph_block(chunk))
        current_paragraph.clear()

    def flush_image_group() -> None:
        if image_group:
            blocks.append(_callout_block("\n".join(image_group)))
            image_group.clear()

    for line in lines:
        stripped = line.strip()

        # Skip empty lines (paragraph boundaries)
        if not stripped:
            flush_paragraph()
            flush_image_group()
            continue

        # Horizontal rules
        if stripped == "---":
            flush_paragraph()
            flush_image_group()
            blocks.append(_paragraph_block("───"))
            continue

        # Image markers — group [IMAGE:], [ALT:], [CAPTION:] together
        if stripped.startswith(("[IMAGE:", "[ALT:", "[CAPTION:")):
            flush_paragraph()
            image_group.append(stripped)
            continue

        # If we were collecting an image group but hit a non-marker line,
        # the image description may have wrapped. Check if it looks like
        # continuation text (no bracket prefix, image_group is open).
        if image_group and not stripped.startswith(("[", "#", "TITLE:", "SUBTITLE:", "TEMPLATE:", "SOURCES:")):
            # Continuation of the previous image marker line
            image_group[-1] += " " + stripped
            continue

        # Flush any pending image group before processing other block types
        flush_image_group()

        # Headings
        if stripped.startswith("### "):
            flush_paragraph()
            blocks.append(_heading_block(stripped[4:], level=3))
        elif stripped.startswith("## "):
            flush_paragraph()
            blocks.append(_heading_block(stripped[3:], level=2))
        elif stripped.startswith("# "):
            flush_paragraph()
            blocks.append(_heading_block(stripped[2:], level=1))
        elif stripped.upper().startswith(("TITLE:", "SUBTITLE:", "TEMPLATE:", "SOURCES:")):
            flush_paragraph()
            blocks.append(_heading_block(stripped, level=2))
        # Footnote lines like [1] Description — URL
        elif stripped.startswith("[") and stripped[1:3].replace("]", "").isdigit():
            flush_paragraph()
            blocks.append(_paragraph_block(stripped))
        # Regular text — accumulate into current paragraph
        else:
            current_paragraph.append(stripped)

    # Flush any remaining content
    flush_paragraph()
    flush_image_group()

    return blocks if blocks else [_paragraph_block("")]


def _paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text[:_BLOCK_CHAR_LIMIT]}}]
        },
    }


def _heading_block(text: str, level: int = 2) -> dict:
    heading_type = f"heading_{min(level, 3)}"
    return {
        "object": "block",
        "type": heading_type,
        heading_type: {
            "rich_text": [{"type": "text", "text": {"content": text[:_BLOCK_CHAR_LIMIT]}}]
        },
    }


def _callout_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "🖼️"},
            "rich_text": [{"type": "text", "text": {"content": text[:_BLOCK_CHAR_LIMIT]}}],
        },
    }


def _split_text(text: str, max_len: int) -> list[str]:
    """Split text into chunks at sentence boundaries, respecting max_len."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Find last sentence end before max_len
        cut = text.rfind(". ", 0, max_len)
        if cut == -1:
            cut = text.rfind(" ", 0, max_len)
        if cut == -1:
            cut = max_len
        else:
            cut += 1  # include the period/space
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return chunks


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

        Uses the Notion REST API directly (with explicit API version header)
        because the notion-client SDK may use a different API version that
        doesn't return properties. Safe to call multiple times — Notion
        ignores properties that already exist.

        Should be called once before the first staging run.
        """
        import httpx

        properties = {
            "Platform": {"select": {"options": [
                {"name": "Substack"}, {"name": "Twitter"},
                {"name": "Linkedin"}, {"name": "Instagram"},
            ]}},
            "Composite Score": {"number": {}},
            "Score Breakdown": {"rich_text": {}},
            "Generated At": {"date": {}},
            "Topic ID": {"rich_text": {}},
            "Thesis Provided": {"checkbox": {}},
            "Model Used": {"rich_text": {}},
            "Token Cost": {"number": {}},
            # Note: "Status" is NOT created here — it already exists as a
            # native Notion status property on the database. We use it as-is.
        }

        try:
            async with httpx.AsyncClient() as http:
                resp = await http.patch(
                    f"https://api.notion.com/v1/databases/{self._database_id}",
                    headers={
                        "Authorization": f"Bearer {self._client.options.auth}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json",
                    },
                    json={"properties": properties},
                )
                resp.raise_for_status()
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
            "Status": {"status": {"name": "Draft"}},
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

        children = _content_to_blocks(content)

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
