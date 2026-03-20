/**
 * POST /api/create-topics — Proxy route for creating topics from research articles.
 *
 * Accepts an array of article objects and forwards them to the Worker's
 * /api/create-topics endpoint, which creates topic records in Postgres
 * bypassing the normal discovery → scoring pipeline.
 *
 * Request body: { articles: Array<{ title: string; url: string; body_preview?: string; source?: string }> }
 * Response: { created: number; skipped: number; topic_ids: string[] }
 *
 * @throws 400 if articles is missing, not an array, or empty
 * @throws 502 if the Worker API is unreachable or returns an error
 */
import { NextRequest, NextResponse } from "next/server";

import { createTopicsFromArticles, WorkerClientError } from "@/lib/worker-client";

export async function POST(request: NextRequest) {
  const { articles } = await request.json();

  if (!articles || !Array.isArray(articles) || articles.length === 0) {
    return NextResponse.json(
      { error: "articles array required" },
      { status: 400 }
    );
  }

  try {
    const result = await createTopicsFromArticles(articles);
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
