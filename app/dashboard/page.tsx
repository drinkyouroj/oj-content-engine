/**
 * app/dashboard/page.tsx — Dashboard overview (Server Component).
 *
 * Implements PRD Section 5 (Approval UI). Loads all dashboard data
 * server-side in a single parallel Promise.all, then passes results
 * to presentational child components. No client-side JavaScript emitted
 * by this route — all data is fetched at request time from Neon Postgres.
 *
 * Data flow:
 *   Neon Postgres → getDashboardStats / getTopicsNeedingAttention / getRecentDrafts
 *   → StatsCards / TopicList / RecentDrafts (Server Components)
 *   → DashboardLayout (ml-[220px] main, fixed sidebar)
 */

// Force dynamic rendering — this page fetches live data from Neon Postgres
// and must not be statically prerendered at build time.
export const dynamic = "force-dynamic";

import { getDashboardStats, getTopicsNeedingAttention, getRecentDrafts } from "@/lib/db";
import { StatsCards } from "@/components/stats-cards";
import { TopicList } from "@/components/topic-list";
import { RecentDrafts } from "@/components/recent-drafts";
import type { TopicRow } from "@/components/topic-list";
import type { DraftRow } from "@/components/recent-drafts";

/**
 * Dashboard overview page. Fetches aggregate stats, active topics, and
 * recent drafts in parallel, then renders a three-section layout.
 *
 * @returns Full dashboard page with stats cards, topic table, and drafts table
 * @throws Propagates DatabaseError if any Postgres query fails (caught by error.tsx)
 */
export default async function DashboardPage() {
  const [stats, topics, drafts] = await Promise.all([
    getDashboardStats(),
    getTopicsNeedingAttention(),
    getRecentDrafts(),
  ]);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      <StatsCards {...stats} />

      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Topics Needing Attention</h2>
        <TopicList topics={topics as TopicRow[]} />
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-4">Recent Drafts</h2>
        <RecentDrafts drafts={drafts as DraftRow[]} />
      </div>
    </div>
  );
}
