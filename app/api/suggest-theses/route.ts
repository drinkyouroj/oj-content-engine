/**
 * app/api/suggest-theses/route.ts — Proxy route for thesis suggestion generation.
 *
 * Forwards POST requests to the Worker's /api/suggest-theses/:topicId endpoint,
 * which fetches the source article, combines it with score data, and calls
 * Claude Haiku to produce 3-5 candidate thesis statements.
 *
 * This route is server-side only. WORKER_URL and WORKER_SECRET are never
 * exposed to the browser.
 *
 * Request body: { topicId: string }
 * Response: { theses: string[] } on success
 *           { theses: [], error: string } on Worker error (status 502)
 *           { error: string } on bad request (status 400)
 *
 * Triggers: Worker /api/suggest-theses/:topicId (blocking, ~5-15s).
 */

import { NextRequest, NextResponse } from "next/server";
import { suggestTheses, WorkerClientError } from "@/lib/worker-client";

/**
 * POST /api/suggest-theses
 *
 * Generates 3-5 thesis suggestions for the given topic by delegating to the
 * Worker layer. Blocks until the Worker returns (estimated 5-15s).
 *
 * @param request - JSON body must contain `topicId` (UUID string)
 * @returns { theses: string[] } on success, or error JSON on failure
 */
export async function POST(request: NextRequest) {
  const { topicId } = await request.json();
  if (!topicId) {
    return NextResponse.json({ error: "topicId required" }, { status: 400 });
  }

  try {
    const result = await suggestTheses(topicId);
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof WorkerClientError) {
      return NextResponse.json(
        { theses: [], error: error.message },
        { status: error.status || 502 }
      );
    }
    throw error;
  }
}
