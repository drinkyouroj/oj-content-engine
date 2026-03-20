/**
 * lib/notion-sync.ts — Best-effort Notion page status synchronisation.
 *
 * Implements PRD Section 6 (Notion Integration — status mirroring). Called
 * after approve and reject actions to keep Notion draft pages in sync with
 * Postgres. Failures are non-fatal: the primary state lives in Postgres, and
 * Notion sync is a convenience layer only.
 *
 * Inputs:  NOTION_API_KEY environment variable.
 * Outputs: true if all page updates succeeded (or if there were no pages to
 *          update / no API key configured), false if any update failed.
 *
 * This module is safe to import in API routes. It uses the Notion REST API
 * directly (no SDK) to keep the dependency surface minimal.
 */

/**
 * Updates the Status property on one or more Notion pages.
 *
 * Called after approve (status = "Approved") or reject (status = "Killed")
 * to mirror the decision into Notion. Each page is updated sequentially to
 * avoid Notion API rate limits. If any update fails, the error is logged and
 * the function returns false, but remaining pages are still attempted.
 *
 * No-ops silently if NOTION_API_KEY is not set or notionPageIds is empty,
 * returning true so callers treat a missing config as success.
 *
 * @param notionPageIds Array of Notion page UUIDs to update
 * @param status        The target Status property value ("Approved" | "Killed")
 * @returns true if all updates succeeded or were skipped; false if any failed
 */
export async function syncNotionStatus(
  notionPageIds: string[],
  status: "Approved" | "Killed"
): Promise<boolean> {
  const apiKey = process.env.NOTION_API_KEY;
  if (!apiKey || notionPageIds.length === 0) return true;

  let allSucceeded = true;

  for (const pageId of notionPageIds) {
    try {
      const response = await fetch(`https://api.notion.com/v1/pages/${pageId}`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Notion-Version": "2022-06-28",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          properties: {
            Status: { status: { name: status } },
          },
        }),
      });
      if (!response.ok) {
        console.error(`Notion sync failed for ${pageId}:`, await response.text());
        allSucceeded = false;
      }
    } catch (error) {
      console.error(`Notion sync error for ${pageId}:`, error);
      allSucceeded = false;
    }
  }

  return allSucceeded;
}
