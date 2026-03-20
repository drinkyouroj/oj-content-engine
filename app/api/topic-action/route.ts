/**
 * POST /api/topic-action — Snooze or kill a topic.
 *
 * Applies a lightweight status transition to a topic without the full
 * approve/reject flow. 'kill' also kills all associated drafts (handled
 * by updateTopicStatus in lib/db). No Notion sync — these are intermediate
 * states, not final decisions.
 *
 * Request body: { topicId: string, action: "snooze" | "kill" }
 * Response: { success: true }
 * Errors: 400 if topicId or action missing, or action not 'snooze'/'kill'
 *
 * Implements PRD Section 5 (Approval UI — topic triage actions).
 */

import { NextRequest, NextResponse } from "next/server";
import { updateTopicStatus } from "@/lib/db";

export async function POST(request: NextRequest) {
  const { topicId, action } = await request.json();
  if (!topicId || !action) {
    return NextResponse.json({ error: "topicId and action required" }, { status: 400 });
  }
  if (action !== "snooze" && action !== "kill") {
    return NextResponse.json({ error: "action must be 'snooze' or 'kill'" }, { status: 400 });
  }

  const status = action === "snooze" ? "snoozed" : "killed";
  await updateTopicStatus(topicId, status);
  return NextResponse.json({ success: true });
}
