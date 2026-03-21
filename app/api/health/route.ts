/**
 * GET /api/health — Fetch unresolved system health alerts for the dashboard.
 *
 * Returns alerts written by the Worker layer (e.g. consecutive RSS fetch
 * failures, Notion write errors). The dashboard health panel polls this
 * endpoint to surface operational issues without requiring a Worker call.
 *
 * Response:
 *   { alerts: Array<{ source, alertType, consecutiveFailures,
 *                     lastFailureAt, resolvedAt }> }
 * Errors: 500 on DB failure (thrown, not caught — let Next.js error boundary handle)
 *
 * Implements PRD Section 5 (Approval UI — health panel) and Section 8
 * (Worker Layer — system_alerts table).
 */

import { NextResponse } from "next/server";
import { getHealthAlerts } from "@/lib/db";

export async function GET() {
  const alerts = await getHealthAlerts();
  return NextResponse.json({
    alerts: alerts.map((a: Record<string, unknown>) => ({
      source: a.source,
      alertType: a.alert_type,
      consecutiveFailures: a.consecutive_failures,
      lastFailureAt: a.last_failure_at,
      resolvedAt: a.resolved_at,
    })),
  });
}
