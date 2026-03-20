# Notion Integration

## Purpose
Stages generated content drafts in Notion's Second Brain database for Justin's review.
Implements PRD Section 6.

## Structure
- `client.py` — Rate-limited Notion API wrapper
- `staging.py` — Draft → Notion page creation with bidirectional linking

## How it fits in the pipeline
Input: ContentDraft rows from generation engine.
Output: Notion pages in the Second Brain database, page IDs stored back on ContentDraft rows.

## Environment variables
- `NOTION_API_KEY` — Notion integration token
- `NOTION_DB_ID` — Second Brain database ID
