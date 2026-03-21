/**
 * POST /api/create-topic — Create one synthesized topic from multiple research articles.
 *
 * Accepts an array of article objects and forwards them to the Worker's
 * /api/create-topic endpoint, which synthesizes a single topic from the
 * combined articles, storing all source URLs for reference.
 *
 * Request body: { articles: Array<{ title: string; url: string; body_preview?: string; source?: string }> }
 * Response: { topic_id: string; title: string; source_count: number }
 */
import { NextRequest, NextResponse } from "next/server";

import { createTopicFromArticles, WorkerClientError } from "@/lib/worker-client";

export async function POST(request: NextRequest) {
  const { articles } = await request.json();

  if (!articles || !Array.isArray(articles) || articles.length === 0) {
    return NextResponse.json(
      { error: "articles array required" },
      { status: 400 }
    );
  }

  try {
    const result = await createTopicFromArticles(articles);
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
