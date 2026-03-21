/**
 * POST /api/regenerate — Trigger content regeneration for a topic.
 *
 * Delegates to the Worker layer via lib/worker-client.ts. The Worker resets
 * the topic to 'queued' and enqueues an ARQ generation job. This endpoint
 * returns immediately with the ARQ job ID — generation completes async.
 *
 * Requires WORKER_URL and WORKER_SECRET to be set; throws WorkerClientError
 * if either is missing or if the Worker responds with a non-2xx status.
 *
 * Request body: { topicId: string }
 * Response: { success: true, jobId: string }
 * Errors: 400 if topicId missing; 502 on Worker API error; 500 on unhandled error
 *
 * Implements PRD Section 5 (Approval UI — Regenerate action) and Section 8
 * (Worker Layer — ARQ job enqueueing).
 */

import { NextRequest, NextResponse } from "next/server";
import { triggerRegeneration, WorkerClientError } from "@/lib/worker-client";

export async function POST(request: NextRequest) {
  const { topicId } = await request.json();
  if (!topicId) {
    return NextResponse.json({ error: "topicId required" }, { status: 400 });
  }

  try {
    const result = await triggerRegeneration(topicId);
    return NextResponse.json({ success: true, jobId: result.jobId });
  } catch (error) {
    if (error instanceof WorkerClientError) {
      return NextResponse.json(
        { success: false, error: error.message },
        { status: error.status || 502 }
      );
    }
    throw error;
  }
}
