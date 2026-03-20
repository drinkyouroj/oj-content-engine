/**
 * components/recent-drafts.tsx — Recent drafts grouped by topic.
 *
 * Displays generated content grouped by topic, with platform tabs inside
 * each group linking to the Notion staging page.
 */

import { Badge } from "@/components/ui/badge";
import Link from "next/link";

export interface DraftRow {
  id: string;
  topic_id: string;
  platform: string;
  status: string;
  notion_page_id: string | null;
  topic_title: string;
}

const PLATFORM_META: Record<string, { emoji: string; label: string }> = {
  substack: { emoji: "📝", label: "Substack" },
  twitter: { emoji: "🐦", label: "Twitter" },
  linkedin: { emoji: "💼", label: "LinkedIn" },
  instagram: { emoji: "📷", label: "Instagram" },
};

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

interface TopicGroup {
  topicId: string;
  topicTitle: string;
  status: string;
  drafts: DraftRow[];
}

function groupByTopic(drafts: DraftRow[]): TopicGroup[] {
  const groups = new Map<string, TopicGroup>();

  for (const draft of drafts) {
    let group = groups.get(draft.topic_id);
    if (!group) {
      group = {
        topicId: draft.topic_id,
        topicTitle: draft.topic_title,
        status: draft.status,
        drafts: [],
      };
      groups.set(draft.topic_id, group);
    }
    group.drafts.push(draft);
  }

  return Array.from(groups.values());
}

interface RecentDraftsProps {
  drafts: DraftRow[];
}

export function RecentDrafts({ drafts }: RecentDraftsProps) {
  if (drafts.length === 0) {
    return (
      <p className="text-zinc-500 text-sm py-4">
        No drafts generated yet.
      </p>
    );
  }

  const groups = groupByTopic(drafts);

  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <div
          key={group.topicId}
          className="rounded-xl bg-zinc-900 border border-zinc-800 overflow-hidden"
        >
          {/* Topic header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
            <Link
              href={`/dashboard/review/${group.topicId}`}
              className="text-sm font-medium text-zinc-200 hover:text-[#00B4D8] transition-colors truncate max-w-md"
            >
              {group.topicTitle}
            </Link>
            <Badge
              variant="outline"
              className={statusBadgeClass(group.status)}
            >
              {group.status}
            </Badge>
          </div>

          {/* Platform links row */}
          <div className="flex items-center gap-1 px-4 py-2">
            {group.drafts.map((draft) => {
              const meta = PLATFORM_META[draft.platform] ?? {
                emoji: "📄",
                label: draft.platform,
              };

              if (draft.notion_page_id) {
                return (
                  <a
                    key={draft.id}
                    href={`https://notion.so/${draft.notion_page_id.replace(/-/g, "")}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-[#00B4D8] transition-colors"
                  >
                    {meta.emoji} {meta.label} ↗
                  </a>
                );
              }

              return (
                <span
                  key={draft.id}
                  className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium bg-zinc-800/50 text-zinc-500"
                >
                  {meta.emoji} {meta.label}
                </span>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
