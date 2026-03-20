/**
 * POST /api/research — Proxy route for topic research search.
 *
 * Accepts a free-text query and forwards it to the Worker's /api/research
 * endpoint, which searches existing signals and Brave Search for relevant
 * articles. Returns a unified list of research results.
 *
 * Request body: { query: string }
 * Response: { results: Array<{ title, url, body_preview, source, published_at }>, warnings: string[] }
 *
 * @throws 400 if query is missing or not a string
 * @throws 502 if the Worker API is unreachable or returns an error
 */
import { NextRequest, NextResponse } from "next/server";

import { searchResearch, WorkerClientError } from "@/lib/worker-client";

export async function POST(request: NextRequest) {
  const { query } = await request.json();

  if (!query || typeof query !== "string") {
    return NextResponse.json({ error: "query required" }, { status: 400 });
  }

  try {
    const result = await searchResearch(query.trim());
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof WorkerClientError) {
      return NextResponse.json(
        { error: error.message },
        { status: error.status || 502 }
      );
    }
    throw error;
  }
}
