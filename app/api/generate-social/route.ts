/**
 * POST /api/generate-social — Generate social content for a single platform.
 *
 * Delegates to the Worker layer via lib/worker-client.ts. The Worker fetches
 * the existing Substack draft, then calls Claude Haiku 4.5 to generate
 * platform-specific content derived from the article. This is a synchronous
 * call that blocks until generation completes (5-15s).
 *
 * Request body: { topicId: string, platform: "twitter" | "linkedin" | "instagram" }
 * Response: { success: true, draft_id: string, platform: string }
 * Errors: 400 if topicId/platform missing or invalid; 502 on Worker error; 500 on unhandled
 *
 * Implements the on-demand social generation flow where Substack is generated
 * first, then social content is derived from it at the reviewer's request.
 */

import { NextRequest, NextResponse } from "next/server";
import { triggerSocialGeneration, WorkerClientError } from "@/lib/worker-client";

const VALID_PLATFORMS = ["twitter", "linkedin", "instagram"] as const;
type SocialPlatform = (typeof VALID_PLATFORMS)[number];

function isValidPlatform(value: string): value is SocialPlatform {
  return (VALID_PLATFORMS as readonly string[]).includes(value);
}

export async function POST(request: NextRequest) {
  const { topicId, platform } = await request.json();

  if (!topicId) {
    return NextResponse.json({ error: "topicId required" }, { status: 400 });
  }

  if (!platform || !isValidPlatform(platform)) {
    return NextResponse.json(
      { error: `platform must be one of: ${VALID_PLATFORMS.join(", ")}` },
      { status: 400 }
    );
  }

  try {
    const result = await triggerSocialGeneration(topicId, platform);
    return NextResponse.json({
      success: true,
      draft_id: result.draft_id,
      platform: result.platform,
    });
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
