/**
 * POST /api/reject — Reject a topic and kill its drafts.
 *
 * Marks all content_drafts as 'killed', sets topic status to 'killed', records
 * the rejection reason, and optionally inserts a scoring_adjustment row to
 * influence future triage. Fires a best-effort Notion sync to "Killed".
 *
 * Request body:
 *   { topicId: string, reason: string, adjustKeyword?: string,
 *     adjustDimension?: string, adjustDelta?: number }
 * Response: { success: true, notionSyncFailed?: true }
 * Errors: 400 if topicId or reason missing; 500 on DB failure
 *
 * Implements PRD Section 5 (Approval UI — Reject action) and Section 3
 * (scoring adjustment feedback loop).
 */

import { NextRequest, NextResponse } from "next/server";
import { rejectTopic, getDraftsForTopic } from "@/lib/db";
import { syncNotionStatus } from "@/lib/notion-sync";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { topicId, reason, adjustKeyword, adjustDimension, adjustDelta } = body;

  if (!topicId || !reason) {
    return NextResponse.json({ error: "topicId and reason required" }, { status: 400 });
  }

  const adjustment = adjustKeyword
    ? {
        keyword: adjustKeyword,
        dimension: adjustDimension || "brand_angle_availability",
        delta: Number(adjustDelta) || 0,
      }
    : undefined;

  // Fetch draft Notion page IDs before the reject write kills them
  const drafts = await getDraftsForTopic(topicId);
  await rejectTopic(topicId, reason, adjustment);

  const notionPageIds = (drafts as Array<{ notion_page_id: string | null }>)
    .filter((d) => d.notion_page_id)
    .map((d) => d.notion_page_id as string);

  const notionSyncOk = await syncNotionStatus(notionPageIds, "Killed");

  return NextResponse.json({
    success: true,
    notionSyncFailed: !notionSyncOk || undefined,
  });
}
