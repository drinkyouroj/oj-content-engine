/**
 * lib/worker-client.ts — HTTP client for the Worker layer API.
 *
 * Implements the Vercel → Worker call contract defined in the two-layer
 * architecture (CLAUDE.md). All requests are authenticated with a shared
 * secret (WORKER_SECRET) sent as the x-worker-secret header.
 *
 * This module must only be imported in API routes (server-side). Never import
 * it in client components — WORKER_SECRET is not a NEXT_PUBLIC_ variable and
 * must not be exposed to the browser.
 *
 * Inputs:  WORKER_URL, WORKER_SECRET environment variables.
 * Outputs: Typed response objects from the Worker FastAPI endpoints.
 */

/**
 * Error thrown when the Worker API returns a non-OK response or when required
 * environment variables are missing.
 */
export class WorkerClientError extends Error {
  constructor(
    message: string,
    /** HTTP status code from the Worker response, if available. */
    public status?: number
  ) {
    super(message);
    this.name = "WorkerClientError";
  }
}

/**
 * Triggers a content regeneration job on the Worker for a given topic.
 *
 * POSTs to the Worker's /api/regenerate/:topicId endpoint, which enqueues
 * an ARQ job to re-run LLM generation using the current topic thesis and
 * scoring context. The call returns immediately with a job ID; generation
 * completes asynchronously.
 *
 * Callers should poll topic/draft status or listen for a webhook to know
 * when the new drafts are ready.
 *
 * @param topicId UUID of the topic to regenerate content for
 * @returns Object containing the ARQ jobId for tracking
 * @throws WorkerClientError if WORKER_URL or WORKER_SECRET are not configured
 * @throws WorkerClientError if the Worker API returns a non-2xx response
 */
export async function triggerRegeneration(
  topicId: string
): Promise<{ jobId: string }> {
  const workerUrl = process.env.WORKER_URL;
  const workerSecret = process.env.WORKER_SECRET;

  if (!workerUrl || !workerSecret) {
    throw new WorkerClientError("WORKER_URL or WORKER_SECRET not configured");
  }

  const response = await fetch(`${workerUrl}/api/regenerate/${topicId}`, {
    method: "POST",
    headers: {
      "x-worker-secret": workerSecret,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new WorkerClientError(`Worker API error: ${text}`, response.status);
  }

  return response.json() as Promise<{ jobId: string }>;
}
