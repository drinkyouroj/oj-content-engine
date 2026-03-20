/**
 * POST /api/approve — Approve all drafts for a topic.
 *
 * Sets all content_drafts for the topic to 'approved', marks the topic as
 * 'archived', and fires a best-effort Notion status sync to "Approved" for
 * any drafts that have a notion_page_id.
 *
 * Request body: { topicId: string }
 * Response: { success: true, draftsApproved: number, notionSyncFailed?: true }
 * Errors: 400 if topicId missing; 500 on DB failure (thrown, not caught)
 *
 * Implements PRD Section 5 (Approval UI — Approve action).
 */

import { NextRequest, NextResponse } from "next/server";
import { approveTopic } from "@/lib/db";
import { syncNotionStatus } from "@/lib/notion-sync";

export async function POST(request: NextRequest) {
  const { topicId } = await request.json();
  if (!topicId) {
    return NextResponse.json({ error: "topicId required" }, { status: 400 });
  }

  const drafts = await approveTopic(topicId);
  const notionPageIds = (drafts as Array<{ notion_page_id: string | null }>)
    .filter((d) => d.notion_page_id)
    .map((d) => d.notion_page_id as string);

  const notionSyncOk = await syncNotionStatus(notionPageIds, "Approved");

  return NextResponse.json({
    success: true,
    draftsApproved: drafts.length,
    notionSyncFailed: !notionSyncOk || undefined,
  });
}
