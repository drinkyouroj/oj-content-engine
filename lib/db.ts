/**
 * lib/db.ts — Neon serverless database client and SQL query helpers.
 *
 * Implements PRD Section 5 (Approval UI / Dashboard). Provides a thin wrapper
 * around the Neon serverless driver and all SQL query functions used by the
 * Next.js approval UI API routes.
 *
 * Inputs:  DATABASE_URL environment variable (Neon connection string).
 * Outputs: Typed query results for topics, drafts, signals, and health alerts.
 *
 * All write operations are intentionally narrow — they only mutate the fields
 * they own and avoid touching columns managed by the Worker layer.
 */

import { neon } from "@neondatabase/serverless";

/**
 * Creates and returns a Neon SQL query function bound to DATABASE_URL.
 * Called per-request to stay compatible with Vercel's serverless execution model.
 *
 * @returns Neon tagged-template SQL function
 * @throws If DATABASE_URL is not set in the environment
 */
export function getDb() {
  return neon(process.env.DATABASE_URL!);
}

// ---- Dashboard queries ----

/**
 * Returns aggregate counts used by the approval dashboard header stats.
 *
 * Runs four COUNT queries in parallel to minimise latency on the hot path.
 *
 * @returns Object with needReview, queued, draftsReady, signalsToday counts
 * @throws DatabaseError if any Postgres query fails
 */
export async function getDashboardStats() {
  const sql = getDb();
  const [reviewCount, queuedCount, draftsCount, signalsToday] =
    await Promise.all([
      sql`SELECT COUNT(*)::int AS count FROM topics WHERE status = 'review'`,
      sql`SELECT COUNT(*)::int AS count FROM topics WHERE status = 'queued'`,
      sql`SELECT COUNT(*)::int AS count FROM content_drafts WHERE status = 'draft'`,
      sql`SELECT COUNT(*)::int AS count FROM signals WHERE discovered_at > NOW() - INTERVAL '24 hours'`,
    ]);
  return {
    needReview: reviewCount[0].count as number,
    queued: queuedCount[0].count as number,
    draftsReady: draftsCount[0].count as number,
    signalsToday: signalsToday[0].count as number,
  };
}

/**
 * Fetches topics in active pipeline states, ordered by composite score descending.
 *
 * Joins topics → scored_signals → signals to surface the original signal metadata
 * alongside the scoring data. Capped at 50 rows to keep the dashboard responsive.
 *
 * @returns Array of topic rows with signal and scoring context, up to 50 items
 * @throws DatabaseError if Postgres connection fails
 */
export async function getTopicsNeedingAttention() {
  const sql = getDb();
  return sql`
    SELECT
      t.id,
      t.status,
      t.vertical,
      t.thesis_provided,
      t.created_at,
      ss.composite_score,
      ss.score_breakdown,
      s.title,
      s.url,
      s.source
    FROM topics t
    JOIN scored_signals ss ON t.scored_signal_id = ss.id
    JOIN signals s ON ss.signal_id = s.id
    WHERE t.status IN ('queued', 'review', 'generating', 'generated')
    ORDER BY ss.composite_score DESC
    LIMIT 50
  `;
}

/**
 * Fetches the 10 most recently created content drafts with their topic titles.
 *
 * Used by the dashboard "Recent Drafts" panel. Only returns lightweight metadata;
 * full draft content is fetched lazily via getDraftsForTopic.
 *
 * @returns Array of draft rows with topic title, ordered by created_at desc
 * @throws DatabaseError if Postgres connection fails
 */
export async function getRecentDrafts() {
  const sql = getDb();
  return sql`
    SELECT
      cd.id,
      cd.platform,
      cd.status,
      cd.notion_page_id,
      cd.created_at,
      s.title AS topic_title
    FROM content_drafts cd
    JOIN topics t ON cd.topic_id = t.id
    JOIN scored_signals ss ON t.scored_signal_id = ss.id
    JOIN signals s ON ss.signal_id = s.id
    ORDER BY cd.created_at DESC
    LIMIT 10
  `;
}

// ---- Topic review queries ----

/**
 * Fetches a single topic with full signal and scoring context for the review page.
 *
 * @param topicId UUID of the topic to fetch
 * @returns Topic row with joined signal and scoring fields, or null if not found
 * @throws DatabaseError if Postgres connection fails
 */
export async function getTopicWithDetails(topicId: string) {
  const sql = getDb();
  const rows = await sql`
    SELECT
      t.*,
      ss.composite_score,
      ss.score_breakdown,
      s.title AS signal_title,
      s.url AS signal_url,
      s.source,
      s.body_preview,
      s.discovered_at
    FROM topics t
    JOIN scored_signals ss ON t.scored_signal_id = ss.id
    JOIN signals s ON ss.signal_id = s.id
    WHERE t.id = ${topicId}::uuid
  `;
  return rows[0] || null;
}

/**
 * Fetches all content drafts for a given topic, ordered by platform.
 *
 * @param topicId UUID of the parent topic
 * @returns Array of content_drafts rows ordered by platform name
 * @throws DatabaseError if Postgres connection fails
 */
export async function getDraftsForTopic(topicId: string) {
  const sql = getDb();
  return sql`
    SELECT *
    FROM content_drafts
    WHERE topic_id = ${topicId}::uuid
    ORDER BY platform
  `;
}

// ---- Write operations ----

/**
 * Approves all draft content for a topic and marks the topic as archived.
 *
 * Sets content_drafts.status = 'approved' for all drafts in 'draft' state,
 * then marks the topic as 'archived'. Returns the approved draft IDs and
 * Notion page IDs so the caller can trigger Notion status updates if needed.
 *
 * @param topicId UUID of the topic to approve
 * @returns Array of approved draft rows containing id and notion_page_id
 * @throws DatabaseError if Postgres connection fails
 */
export async function approveTopic(topicId: string) {
  const sql = getDb();
  const drafts = await sql`
    UPDATE content_drafts SET status = 'approved'
    WHERE topic_id = ${topicId}::uuid AND status = 'draft'
    RETURNING id, notion_page_id
  `;
  await sql`
    UPDATE topics SET status = 'archived'
    WHERE id = ${topicId}::uuid
  `;
  return drafts;
}

/**
 * Rejects a topic, kills its drafts, records the rejection reason, and
 * optionally inserts a scoring adjustment to influence future triage.
 *
 * The optional `adjustment` parameter lets reviewers teach the scoring layer
 * by associating a keyword + dimension delta with the rejection. Adjustments
 * are applied by the Worker's Pass 1 scorer on subsequent runs.
 *
 * @param topicId   UUID of the topic to reject
 * @param reason    Human-readable rejection reason stored on the topic row
 * @param adjustment Optional scoring nudge: keyword, dimension, and signed delta (-20..+20)
 * @throws DatabaseError if any Postgres write fails
 */
export async function rejectTopic(
  topicId: string,
  reason: string,
  adjustment?: { keyword: string; dimension: string; delta: number }
) {
  const sql = getDb();
  await sql`
    UPDATE content_drafts SET status = 'killed'
    WHERE topic_id = ${topicId}::uuid
  `;
  await sql`
    UPDATE topics SET status = 'killed', review_decision = ${reason}
    WHERE id = ${topicId}::uuid
  `;
  if (adjustment) {
    await sql`
      INSERT INTO scoring_adjustments (id, keyword, dimension, adjustment, created_by, created_at, updated_at)
      VALUES (gen_random_uuid(), ${adjustment.keyword}, ${adjustment.dimension}, ${adjustment.delta}, 'dashboard', NOW(), NOW())
    `;
  }
}

/**
 * Saves a human-provided thesis to a topic and marks thesis_provided = true.
 *
 * The thesis is passed to the generation prompt by the Worker when it picks
 * up the topic. Saving here does not trigger generation — the UI must call
 * triggerRegeneration separately if regeneration is desired.
 *
 * @param topicId UUID of the topic to update
 * @param thesis  Thesis text provided by the reviewer
 * @throws DatabaseError if Postgres connection fails
 */
export async function saveThesis(topicId: string, thesis: string) {
  const sql = getDb();
  await sql`
    UPDATE topics SET thesis = ${thesis}, thesis_provided = true
    WHERE id = ${topicId}::uuid
  `;
}

/**
 * Updates a topic's status field. If the new status is 'killed', also kills
 * all associated content drafts to keep referential consistency.
 *
 * @param topicId UUID of the topic to update
 * @param status  New status value (must match the topics.status enum)
 * @throws DatabaseError if Postgres connection fails
 */
export async function updateTopicStatus(topicId: string, status: string) {
  const sql = getDb();
  await sql`
    UPDATE topics SET status = ${status}
    WHERE id = ${topicId}::uuid
  `;
  if (status === "killed") {
    await sql`
      UPDATE content_drafts SET status = 'killed'
      WHERE topic_id = ${topicId}::uuid
    `;
  }
}

/**
 * Fetches unresolved system health alerts ordered by creation time descending.
 *
 * Used by the dashboard health panel to surface Worker-side failures (e.g.
 * consecutive RSS fetch failures, Notion write errors). Alerts are written
 * by the Worker and resolved either automatically on success or manually
 * via the admin interface.
 *
 * @returns Array of unresolved system_alerts rows, up to 20 items
 * @throws DatabaseError if Postgres connection fails
 */
export async function getHealthAlerts() {
  const sql = getDb();
  return sql`
    SELECT source, alert_type, consecutive_failures, last_failure_at, resolved_at
    FROM system_alerts
    WHERE resolved_at IS NULL
    ORDER BY created_at DESC
    LIMIT 20
  `;
}
