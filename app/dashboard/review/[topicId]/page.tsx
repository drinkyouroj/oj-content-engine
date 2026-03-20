/**
 * app/dashboard/review/[topicId]/page.tsx — Topic review page (Server Component).
 *
 * Implements PRD Section 5 (Approval UI). This is the core workflow page where
 * the reviewer examines a topic's signal, score breakdown, and generated drafts,
 * writes or edits a thesis, and takes an action (approve, reject, regenerate,
 * snooze, or kill).
 *
 * Data is fetched server-side via getTopicWithDetails and getDraftsForTopic.
 * Interactive elements (ThesisInput, TopicActions, Tabs) are client components
 * rendered within this server page.
 *
 * Inputs:  params.topicId — UUID from the dynamic route segment.
 * Outputs: Full review page with score breakdown, thesis editor, draft tabs, actions.
 */

import { getTopicWithDetails, getDraftsForTopic } from "@/lib/db";
import { ScoreBreakdown } from "@/components/score-breakdown";
import { ThesisInput } from "@/components/thesis-input";
import { DraftPreview } from "@/components/draft-preview";
import { TopicActions } from "@/components/topic-actions";
import { Badge } from "@/components/ui/badge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { notFound } from "next/navigation";
import Link from "next/link";

export const dynamic = "force-dynamic";

/** Platform display config: emoji prefix and human-readable label. */
const PLATFORM_META: Record<string, { emoji: string; label: string }> = {
  substack: { emoji: "\uD83D\uDCDD", label: "Substack" },
  twitter: { emoji: "\uD83D\uDC26", label: "Twitter" },
  linkedin: { emoji: "\uD83D\uDCBC", label: "LinkedIn" },
  instagram: { emoji: "\uD83D\uDCF7", label: "Instagram" },
};

/**
 * Returns className overrides for a status Badge to match brand colours.
 * Mirrors the logic in topic-list.tsx for consistency.
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
    case "archived":
      return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
    case "killed":
      return "bg-red-500/20 text-red-400 border-red-500/30";
    default:
      return "bg-zinc-700/40 text-zinc-400 border-zinc-600/30";
  }
}

/**
 * Formats a date string or Date into a readable short date.
 *
 * @param date ISO date string or Date object
 * @returns Formatted date string (e.g. "Mar 20, 2026")
 */
function formatDate(date: string | Date): string {
  return new Date(date).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Server-rendered topic review page.
 *
 * Fetches topic details and drafts in parallel, then renders a full review
 * layout: header with score, score breakdown bars, thesis editor, tabbed
 * draft previews, and action buttons.
 *
 * @param params Promise containing topicId from the dynamic route segment
 */
export default async function ReviewPage({
  params,
}: {
  params: Promise<{ topicId: string }>;
}) {
  const { topicId } = await params;

  const [topic, drafts] = await Promise.all([
    getTopicWithDetails(topicId),
    getDraftsForTopic(topicId),
  ]);

  if (!topic) {
    notFound();
  }

  // Parse score_breakdown from JSONB (may already be an object)
  const scoreBreakdown: Record<string, number> =
    typeof topic.score_breakdown === "string"
      ? JSON.parse(topic.score_breakdown)
      : topic.score_breakdown ?? {};

  // Determine which platforms have drafts
  const draftsWithMeta = drafts.map((d: Record<string, unknown>) => {
    return {
      id: d.id as string,
      content: d.content as string,
      platform: d.platform as string,
      model_used: d.model_used as string | null,
      notion_page_id: d.notion_page_id as string | null,
      generation_metadata: d.generation_metadata as Record<string, unknown> | null,
      platformKey: String(d.platform ?? "").toLowerCase(),
    };
  });

  // base-ui Tabs uses numeric indices, not string values
  const defaultTab = 0;

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      {/* Back link */}
      <Link
        href="/dashboard"
        className="text-sm text-zinc-500 hover:text-zinc-300"
      >
        &larr; Back to dashboard
      </Link>

      {/* ---- Header ---- */}
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1 space-y-2">
            <h1 className="text-2xl font-bold text-zinc-100">
              {topic.signal_title}
            </h1>

            <div className="flex flex-wrap items-center gap-3">
              {topic.signal_url && (
                <a
                  href={topic.signal_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-[#00B4D8] hover:underline"
                >
                  Source &uarr;
                </a>
              )}

              {topic.discovered_at && (
                <span className="text-xs text-zinc-500">
                  Discovered {formatDate(topic.discovered_at)}
                </span>
              )}

              {topic.source && (
                <span className="text-xs text-zinc-600">
                  via {topic.source}
                </span>
              )}

              <Badge
                variant="outline"
                className={statusBadgeClass(topic.status)}
              >
                {topic.status}
              </Badge>

              {topic.vertical && (
                <Badge variant="secondary" className="text-zinc-400">
                  {topic.vertical}
                </Badge>
              )}
            </div>
          </div>

          {/* Large composite score */}
          <div className="flex flex-col items-center">
            <span className="font-mono text-4xl font-bold text-[#00B4D8]">
              {topic.composite_score ?? "—"}
            </span>
            <span className="text-xs text-zinc-500">composite</span>
          </div>
        </div>

        {/* Body preview if available */}
        {topic.body_preview && (
          <p className="text-sm leading-relaxed text-zinc-400">
            {topic.body_preview}
          </p>
        )}
      </div>

      {/* ---- Score Breakdown ---- */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">
          Score Breakdown
        </h2>
        <ScoreBreakdown breakdown={scoreBreakdown} />
      </section>

      <Separator className="bg-zinc-800" />

      {/* ---- Thesis Input ---- */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">Thesis</h2>
        <ThesisInput
          topicId={topicId}
          thesis={topic.thesis ?? null}
          thesisProvided={topic.thesis_provided ?? false}
        />
      </section>

      <Separator className="bg-zinc-800" />

      {/* ---- Draft Tabs ---- */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">Drafts</h2>

        {draftsWithMeta.length === 0 ? (
          <p className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-6 text-center text-sm text-zinc-500">
            No drafts generated yet. Write a thesis and hit Regenerate to kick
            off content generation.
          </p>
        ) : (
          <Tabs defaultValue={defaultTab}>
            <TabsList className="mb-4">
              {draftsWithMeta.map((draft, index) => {
                const meta = PLATFORM_META[draft.platformKey];
                const label = meta
                  ? `${meta.emoji} ${meta.label}`
                  : draft.platformKey;
                return (
                  <TabsTrigger key={draft.id} value={index}>
                    {label}
                  </TabsTrigger>
                );
              })}
            </TabsList>

            {draftsWithMeta.map((draft, index) => (
              <TabsContent key={draft.id} value={index}>
                <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-6">
                  <DraftPreview
                    content={draft.content ?? ""}
                    platform={draft.platform ?? ""}
                    modelUsed={draft.model_used}
                    notionPageId={draft.notion_page_id}
                    generationMetadata={draft.generation_metadata}
                  />
                </div>
              </TabsContent>
            ))}
          </Tabs>
        )}
      </section>

      <Separator className="bg-zinc-800" />

      {/* ---- Actions ---- */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">Actions</h2>
        <TopicActions
          topicId={topicId}
          topicStatus={topic.status}
          hasDrafts={draftsWithMeta.length > 0}
          hasSubstackDraft={draftsWithMeta.some((d) => d.platformKey === "substack")}
          existingPlatforms={draftsWithMeta.map((d) => d.platformKey)}
        />
      </section>
    </div>
  );
}
