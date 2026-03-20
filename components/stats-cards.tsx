/**
 * components/stats-cards.tsx — Dashboard aggregate stat cards.
 *
 * Implements PRD Section 5 (Approval UI). Renders four metric cards across
 * the top of the dashboard showing live counts from Postgres.
 *
 * Inputs:  needReview, queued, draftsReady, signalsToday counts from getDashboardStats()
 * Outputs: Four styled Card components in a responsive 4-column grid.
 */

import { Card, CardContent } from "@/components/ui/card";

interface StatsCardsProps {
  needReview: number;
  queued: number;
  draftsReady: number;
  signalsToday: number;
}

/**
 * Renders four metric cards summarising pipeline state at a glance.
 *
 * @param needReview   Count of topics in 'review' status
 * @param queued       Count of topics in 'queued' status
 * @param draftsReady  Count of content_drafts in 'draft' status
 * @param signalsToday Count of signals discovered in the last 24 hours
 */
export function StatsCards({
  needReview,
  queued,
  draftsReady,
  signalsToday,
}: StatsCardsProps) {
  const stats = [
    { label: "Need Review", value: needReview, color: "text-[#FF6B35]" },
    { label: "Queued", value: queued, color: "text-[#00B4D8]" },
    { label: "Drafts Ready", value: draftsReady, color: "text-green-400" },
    { label: "Signals Today", value: signalsToday, color: "text-zinc-400" },
  ];

  return (
    <div className="grid grid-cols-4 gap-4 mb-8">
      {stats.map((stat) => (
        <Card key={stat.label} className="bg-zinc-900 border-zinc-800">
          <CardContent className="pt-6">
            <div className={`text-3xl font-bold font-mono ${stat.color}`}>
              {stat.value}
            </div>
            <div className="text-sm text-zinc-400 mt-1">{stat.label}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
