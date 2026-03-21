# Notion Database Schema

The pipeline stages drafts in a Notion database ("Second Brain") for human review. Database ID is set via `NOTION_DB_ID`.

## Properties

| Property | Type | Description |
|---|---|---|
| Title | title | Draft headline / topic title |
| Platform | select | Target platform (substack, twitter, linkedin, instagram) |
| Status | status | Workflow state: Not started, In progress, Done |
| Composite Score | number | Overall triage score (0-100) |
| Score Breakdown | rich_text | JSON string of individual dimension scores |
| Generated At | date | Timestamp of draft generation |
| Topic ID | rich_text | UUID linking back to the Postgres topic row |
| Brand Angle | number | Brand fit score (0-100) |
| Thesis Provided | checkbox | Whether a human-provided thesis was used |
| Model Used | rich_text | Claude model ID used for generation |
| Token Cost | number | Estimated token cost of generation |

## Content Format

Draft text is written as Notion blocks:

- **heading_2** — Section headers
- **paragraph** — Body text
- **callout** — Key takeaways or highlighted points

## Comments

Generation metadata is stored as page comments:

```json
{
  "model": "claude-sonnet-4-20250514",
  "timestamp": "2026-03-20T12:00:00Z",
  "metadata": { ... }
}
```

## Status Sync

When a draft is approved or rejected in the dashboard UI:

- **Approved** → Status set to `Done`
- **Killed** → Status set to `Not started`
