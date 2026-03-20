/**
 * components/recent-drafts.tsx — Panel showing the 10 most recent content drafts.
 *
 * Implements PRD Section 5 (Approval UI). Displays draft metadata — platform,
 * topic title, status, and a link to the Notion staging page — without loading
 * full draft body content (fetched lazily on the review page).
 *
 * Inputs:  Array of DraftRow objects from getRecentDrafts()
 * Outputs: shadcn Table with platform emoji, status badge, and Notion link.
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

export interface DraftRow {
  id: string;
  platform: string;
  status: string;
  notion_page_id: string | null;
  topic_title: string;
}

/** Maps platform slug to a display emoji. */
const PLATFORM_EMOJI: Record<string, string> = {
  substack: "📝",
  twitter: "🐦",
  linkedin: "💼",
  instagram: "📷",
};

/**
 * Returns className overrides for a status Badge to match brand colours.
 *
 * @param status Draft status string from the DB enum
 * @returns className string for the Badge component
 */
function statusBadgeClass(status: string): string {
  switch (status) {
    case "draft":
      return "bg-[#00B4D8]/20 text-[#00B4D8] border-[#00B4D8]/30";
    case "approved":
      return "bg-green-500/20 text-green-400 border-green-500/30";
    case "killed":
      return "bg-zinc-700/40 text-zinc-500 border-zinc-600/30";
    default:
      return "bg-zinc-700/40 text-zinc-400 border-zinc-600/30";
  }
}

interface RecentDraftsProps {
  drafts: DraftRow[];
}

/**
 * Table of the 10 most recently created content drafts.
 * Renders an empty state message when no drafts exist yet.
 *
 * @param drafts Array of draft rows from getRecentDrafts()
 */
export function RecentDrafts({ drafts }: RecentDraftsProps) {
  if (drafts.length === 0) {
    return (
      <p className="text-zinc-500 text-sm py-4">
        No drafts generated yet.
      </p>
    );
  }

  return (
    <div className="rounded-xl bg-zinc-900 border border-zinc-800 overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="border-zinc-800 hover:bg-transparent">
            <TableHead className="text-zinc-400 font-medium w-28">Platform</TableHead>
            <TableHead className="text-zinc-400 font-medium">Topic</TableHead>
            <TableHead className="text-zinc-400 font-medium w-28">Status</TableHead>
            <TableHead className="text-zinc-400 font-medium w-24">Notion</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {drafts.map((draft) => {
            const emoji = PLATFORM_EMOJI[draft.platform] ?? "📄";
            return (
              <TableRow
                key={draft.id}
                className="border-zinc-800 hover:bg-zinc-800/50"
              >
                <TableCell>
                  <span className="text-sm text-zinc-300">
                    {emoji}{" "}
                    <span className="capitalize">{draft.platform}</span>
                  </span>
                </TableCell>
                <TableCell className="max-w-xs">
                  <span className="truncate block text-zinc-300 text-sm">
                    {draft.topic_title}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={statusBadgeClass(draft.status)}
                  >
                    {draft.status}
                  </Badge>
                </TableCell>
                <TableCell>
                  {draft.notion_page_id ? (
                    <a
                      href={`https://notion.so/${draft.notion_page_id.replace(/-/g, "")}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-[#00B4D8] hover:underline"
                    >
                      Open ↗
                    </a>
                  ) : (
                    <span className="text-zinc-600 text-xs">—</span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
