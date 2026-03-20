/**
 * POST /api/thesis — Save a reviewer-provided thesis to a topic.
 *
 * Persists the thesis text and sets thesis_provided = true on the topic row.
 * Does NOT trigger regeneration — the UI should call /api/regenerate separately
 * if new drafts are desired after saving the thesis.
 *
 * Request body: { topicId: string, thesis: string }
 * Response: { success: true }
 * Errors: 400 if topicId or thesis missing; 500 on DB failure
 *
 * Implements PRD Section 3.5 (Thesis Injection).
 */

import { NextRequest, NextResponse } from "next/server";
import { saveThesis } from "@/lib/db";

export async function POST(request: NextRequest) {
  const { topicId, thesis } = await request.json();
  if (!topicId || !thesis) {
    return NextResponse.json({ error: "topicId and thesis required" }, { status: 400 });
  }

  await saveThesis(topicId, thesis);
  return NextResponse.json({ success: true });
}
