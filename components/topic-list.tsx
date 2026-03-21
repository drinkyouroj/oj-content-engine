/**
 * components/topic-list.tsx — Table of topics needing pipeline attention.
 *
 * Implements PRD Section 5 (Approval UI). Displays topics in active pipeline
 * states (review, queued, generating, generated) sorted by composite score.
 * Each row links to the full topic review page at /dashboard/review/[id].
 *
 * Inputs:  Array of TopicRow objects from getTopicsNeedingAttention()
 * Outputs: shadcn Table with score colouring, status badges, and nav links.
 */

import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

export interface TopicRow {
  id: string;
  title: string;
  composite_score: number;
  status: string;
  vertical: string | null;
  thesis_provided: boolean;
}

/**
 * Returns a Tailwind colour class for a composite score value.
 * Green ≥ 65, yellow 55–64, red < 55.
 *
 * @param score Composite score (0–100)
 * @returns Tailwind text colour class string
 */
function scoreColour(score: number): string {
  if (score >= 65) return "text-green-400";
  if (score >= 55) return "text-yellow-400";
  return "text-red-400";
}

/**
 * Returns className overrides for a status Badge to match brand colours.
 *
 * @param status Topic status string from the DB enum
 * @returns className string for the Badge component
 */
function statusBadgeClass(status: string): string {
  switch (status) {
    case "review":
      return "bg-[#FF6B35]/20 text-[#FF6B35] border-[#FF6B35]/30";
    case "queued":
      return "bg-[#00B4D8]/20 text-[#00B4D8] border-[#00B4D8]/30";
    case "generating":
      return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
    case "generated":
      return "bg-green-500/20 text-green-400 border-green-500/30";
    default:
      return "bg-zinc-700/40 text-zinc-400 border-zinc-600/30";
  }
}

interface TopicListProps {
  topics: TopicRow[];
}

/**
 * Table of topics ordered by composite score descending.
 * Renders an empty state message when the topics array is empty.
 *
 * @param topics Array of topic rows from getTopicsNeedingAttention()
 */
export function TopicList({ topics }: TopicListProps) {
  if (topics.length === 0) {
    return (
      <p className="text-zinc-500 text-sm py-4">
        No topics need attention right now.
      </p>
    );
  }

  return (
    <div className="rounded-xl bg-zinc-900 border border-zinc-800 overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="border-zinc-800 hover:bg-transparent">
            <TableHead className="text-zinc-400 font-medium">Title</TableHead>
            <TableHead className="text-zinc-400 font-medium w-24">Score</TableHead>
            <TableHead className="text-zinc-400 font-medium w-32">Status</TableHead>
            <TableHead className="text-zinc-400 font-medium w-32">Vertical</TableHead>
            <TableHead className="text-zinc-400 font-medium w-24">Thesis</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {topics.map((topic) => (
            <TableRow
              key={topic.id}
              className="border-zinc-800 hover:bg-zinc-800/50"
            >
              <TableCell className="max-w-xs">
                <Link
                  href={`/dashboard/review/${topic.id}`}
                  className="text-[#00B4D8] hover:underline truncate block"
                >
                  {topic.title}
                </Link>
              </TableCell>
              <TableCell>
                <span
                  className={`font-mono text-sm font-semibold ${scoreColour(topic.composite_score)}`}
                >
                  {topic.composite_score}
                </span>
              </TableCell>
              <TableCell>
                <Badge
                  variant="outline"
                  className={statusBadgeClass(topic.status)}
                >
                  {topic.status}
                </Badge>
              </TableCell>
              <TableCell>
                {topic.vertical ? (
                  <Badge variant="secondary" className="text-zinc-400">
                    {topic.vertical}
                  </Badge>
                ) : (
                  <span className="text-zinc-600 text-xs">—</span>
                )}
              </TableCell>
              <TableCell>
                {topic.thesis_provided ? (
                  <span className="text-green-400 text-sm">✓</span>
                ) : (
                  <span className="text-[#FF6B35] text-xs">needed</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
