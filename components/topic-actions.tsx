"use client";

/**
 * components/topic-actions.tsx — Action buttons for the topic review workflow.
 *
 * Implements PRD Section 5 (Approval UI). Renders Approve, Reject, Regenerate,
 * Snooze, and Kill buttons at the bottom of the review page. Each button POSTs
 * to the corresponding API route and handles loading/disabled state.
 *
 * The Reject action opens a dialog for entering a rejection reason and an
 * optional scoring adjustment (keyword + dimension + delta) that feeds back
 * into the Worker's triage rubric.
 *
 * Inputs:  topicId (UUID), topicStatus (current status string)
 * Outputs: POST calls to /api/approve, /api/reject, /api/regenerate, /api/topic-action
 */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

/** Scoring dimensions available for rejection adjustments. */
const SCORING_DIMENSIONS = [
  { value: "signal_strength", label: "Signal Strength" },
  { value: "timing_window", label: "Timing Window" },
  { value: "depth_potential", label: "Depth Potential" },
  { value: "novelty", label: "Novelty" },
  { value: "community_resonance", label: "Community Resonance" },
  { value: "brand_angle_availability", label: "Brand Angle" },
] as const;

/** Social platforms available for on-demand generation. */
const SOCIAL_PLATFORMS = [
  { key: "twitter" as const, label: "Twitter", emoji: "\uD83D\uDC26" },
  { key: "linkedin" as const, label: "LinkedIn", emoji: "\uD83D\uDCBC" },
  { key: "instagram" as const, label: "Instagram", emoji: "\uD83D\uDCF7" },
];

interface TopicActionsProps {
  topicId: string;
  topicStatus: string;
  hasDrafts: boolean;
  /** Whether a Substack draft exists (enables social generation buttons). */
  hasSubstackDraft: boolean;
  /** List of platform keys that already have drafts generated. */
  existingPlatforms: string[];
}

/**
 * Loading spinner rendered inside action buttons during in-flight requests.
 */
function Spinner() {
  return (
    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
  );
}

/**
 * Action buttons for the topic review page.
 *
 * Provides Approve, Reject (with dialog), Regenerate, Snooze 24h, and Kill Topic
 * buttons. Each action POSTs to the relevant API endpoint and navigates back to
 * the dashboard on terminal actions (approve, reject, kill).
 *
 * @param topicId     UUID of the topic being reviewed
 * @param topicStatus Current status string (used to conditionally disable actions)
 */
export function TopicActions({ topicId, topicStatus, hasDrafts, hasSubstackDraft, existingPlatforms }: TopicActionsProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  // Track which specific action is in-flight so we can show the right spinner
  const [activeAction, setActiveAction] = useState<string | null>(null);

  // Reject dialog state
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [adjustKeyword, setAdjustKeyword] = useState("");
  const [adjustDimension, setAdjustDimension] = useState("");
  const [adjustDelta, setAdjustDelta] = useState("");
  const [error, setError] = useState<string | null>(null);

  /**
   * Generic action handler. POSTs to the given URL with a JSON body,
   * handles errors, and optionally navigates to the dashboard on success.
   *
   * @param url           API endpoint to POST to
   * @param body          JSON-serialisable request body
   * @param actionKey     Unique key for tracking which button is loading
   * @param navigateHome  Whether to navigate to /dashboard after success
   */
  function performAction(
    url: string,
    body: Record<string, unknown>,
    actionKey: string,
    navigateHome: boolean
  ) {
    setError(null);
    setActiveAction(actionKey);

    startTransition(async () => {
      try {
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (!res.ok) {
          const data = (await res.json().catch(() => ({}))) as {
            error?: string;
          };
          setError(data.error ?? `Action failed (${res.status})`);
          setActiveAction(null);
          return;
        }

        if (navigateHome) {
          router.refresh();
          router.push("/dashboard");
        } else {
          router.refresh();
          setActiveAction(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unexpected error");
        setActiveAction(null);
      }
    });
  }

  /** Handles the Approve button click. */
  function handleApprove() {
    performAction("/api/approve", { topicId }, "approve", true);
  }

  /** Handles the Regenerate button click. */
  function handleRegenerate() {
    performAction("/api/regenerate", { topicId }, "regenerate", false);
  }

  /** Handles the Snooze 24h button click. */
  function handleSnooze() {
    performAction(
      "/api/topic-action",
      { topicId, action: "snooze" },
      "snooze",
      false
    );
  }

  /** Handles the Kill Topic button click. */
  function handleKill() {
    performAction(
      "/api/topic-action",
      { topicId, action: "kill" },
      "kill",
      true
    );
  }

  /**
   * Handles the Reject dialog form submission.
   * Builds the adjustment payload only if all three adjustment fields are filled.
   */
  function handleRejectSubmit() {
    if (!rejectReason.trim()) return;

    const body: Record<string, unknown> = {
      topicId,
      reason: rejectReason.trim(),
    };

    // Include scoring adjustment only when all three fields are provided
    if (adjustKeyword.trim() && adjustDimension && adjustDelta) {
      const delta = Number(adjustDelta);
      if (!Number.isNaN(delta) && delta >= -20 && delta <= 20) {
        body.adjustment = {
          keyword: adjustKeyword.trim(),
          dimension: adjustDimension,
          delta,
        };
      }
    }

    setActiveAction("reject");
    setError(null);

    startTransition(async () => {
      try {
        const res = await fetch("/api/reject", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (!res.ok) {
          const data = (await res.json().catch(() => ({}))) as {
            error?: string;
          };
          setError(data.error ?? `Reject failed (${res.status})`);
          setActiveAction(null);
          return;
        }

        setRejectOpen(false);
        router.refresh();
        router.push("/dashboard");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unexpected error");
        setActiveAction(null);
      }
    });
  }

  const isDisabled = isPending;

  return (
    <div className="space-y-3">
      {error && (
        <p className="text-xs text-red-400" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {/* Approve — disabled when no drafts exist */}
        <Button
          onClick={handleApprove}
          disabled={isDisabled || !hasDrafts}
          title={!hasDrafts ? "Generate drafts first before approving" : undefined}
          className="bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
        >
          {activeAction === "approve" ? (
            <span className="flex items-center gap-1.5">
              <Spinner />
              Approving...
            </span>
          ) : (
            "Approve"
          )}
        </Button>

        {/* Reject — opens dialog */}
        <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
          <DialogTrigger
            render={
              <Button
                disabled={isDisabled || !hasDrafts}
                title={!hasDrafts ? "Generate drafts first before rejecting" : undefined}
                className="bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
              />
            }
          >
            {activeAction === "reject" ? (
              <span className="flex items-center gap-1.5">
                <Spinner />
                Rejecting...
              </span>
            ) : (
              "Reject"
            )}
          </DialogTrigger>

          <DialogContent className="bg-zinc-900 text-zinc-100 sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="text-zinc-100">Reject Topic</DialogTitle>
              <DialogDescription className="text-zinc-400">
                Explain why this topic is being rejected. Optionally adjust
                scoring for similar future topics.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 pt-2">
              {/* Reason textarea */}
              <div className="space-y-1.5">
                <label
                  htmlFor="reject-reason"
                  className="text-xs font-medium text-zinc-400"
                >
                  Reason (required)
                </label>
                <Textarea
                  id="reject-reason"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Why is this topic being rejected?"
                  className="min-h-20 resize-none border-zinc-700 bg-zinc-800 text-sm text-zinc-200 placeholder:text-zinc-600"
                />
              </div>

              {/* Optional scoring adjustment */}
              <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-800/50 p-3">
                <p className="text-xs font-medium text-zinc-500">
                  Optional: Scoring Adjustment
                </p>

                {/* Keyword */}
                <div className="space-y-1">
                  <label
                    htmlFor="adjust-keyword"
                    className="text-xs text-zinc-500"
                  >
                    Keyword
                  </label>
                  <input
                    id="adjust-keyword"
                    type="text"
                    value={adjustKeyword}
                    onChange={(e) => setAdjustKeyword(e.target.value)}
                    placeholder="e.g. meme-coin"
                    className="flex h-8 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus-visible:border-[#00B4D8] focus-visible:ring-1 focus-visible:ring-[#00B4D8]/30"
                  />
                </div>

                {/* Dimension dropdown */}
                <div className="space-y-1">
                  <label
                    htmlFor="adjust-dimension"
                    className="text-xs text-zinc-500"
                  >
                    Dimension
                  </label>
                  <select
                    id="adjust-dimension"
                    value={adjustDimension}
                    onChange={(e) => setAdjustDimension(e.target.value)}
                    className="flex h-8 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2 text-sm text-zinc-200 outline-none focus-visible:border-[#00B4D8] focus-visible:ring-1 focus-visible:ring-[#00B4D8]/30"
                  >
                    <option value="">Select dimension...</option>
                    {SCORING_DIMENSIONS.map(({ value, label }) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Delta number input */}
                <div className="space-y-1">
                  <label
                    htmlFor="adjust-delta"
                    className="text-xs text-zinc-500"
                  >
                    Delta (-20 to +20)
                  </label>
                  <input
                    id="adjust-delta"
                    type="number"
                    min={-20}
                    max={20}
                    value={adjustDelta}
                    onChange={(e) => setAdjustDelta(e.target.value)}
                    placeholder="0"
                    className="flex h-8 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 font-mono text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus-visible:border-[#00B4D8] focus-visible:ring-1 focus-visible:ring-[#00B4D8]/30"
                  />
                </div>
              </div>

              {/* Submit */}
              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  onClick={() => setRejectOpen(false)}
                  disabled={isPending}
                  className="text-zinc-400 hover:text-zinc-200"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleRejectSubmit}
                  disabled={isPending || !rejectReason.trim()}
                  className="bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {activeAction === "reject" ? (
                    <span className="flex items-center gap-1.5">
                      <Spinner />
                      Submitting...
                    </span>
                  ) : (
                    "Reject Topic"
                  )}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Regenerate */}
        <Button
          onClick={handleRegenerate}
          disabled={isDisabled}
          className="bg-[#00B4D8] text-zinc-900 hover:bg-[#00B4D8]/90 disabled:opacity-50"
        >
          {activeAction === "regenerate" ? (
            <span className="flex items-center gap-1.5">
              <Spinner />
              Regenerating...
            </span>
          ) : (
            "Regenerate"
          )}
        </Button>

        {/* Snooze 24h */}
        <Button
          onClick={handleSnooze}
          disabled={isDisabled}
          variant="outline"
          className="border-zinc-700 text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
        >
          {activeAction === "snooze" ? (
            <span className="flex items-center gap-1.5">
              <Spinner />
              Snoozing...
            </span>
          ) : (
            "Snooze 24h"
          )}
        </Button>

        {/* Kill Topic */}
        <Button
          onClick={handleKill}
          disabled={isDisabled}
          className="bg-red-900 text-red-200 hover:bg-red-800 disabled:opacity-50"
        >
          {activeAction === "kill" ? (
            <span className="flex items-center gap-1.5">
              <Spinner />
              Killing...
            </span>
          ) : (
            "Kill Topic"
          )}
        </Button>
      </div>

      {/* ---- Social Content Generation (on-demand) ---- */}
      {hasSubstackDraft && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-zinc-500">
            Generate social content from Substack article (Claude Haiku 4.5)
          </p>
          <div className="flex flex-wrap items-center gap-3">
            {SOCIAL_PLATFORMS.map(({ key, label, emoji }) => {
              const alreadyExists = existingPlatforms.includes(key);
              const actionKey = `social-${key}`;
              return (
                <Button
                  key={key}
                  onClick={() =>
                    performAction(
                      "/api/generate-social",
                      { topicId, platform: key },
                      actionKey,
                      false
                    )
                  }
                  disabled={isDisabled}
                  variant="outline"
                  className="border-zinc-700 text-zinc-300 hover:border-[#FF6B35]/50 hover:text-[#FF6B35] disabled:opacity-50"
                >
                  {activeAction === actionKey ? (
                    <span className="flex items-center gap-1.5">
                      <Spinner />
                      Generating...
                    </span>
                  ) : (
                    <span>
                      {emoji} {alreadyExists ? `Regenerate ${label}` : `Generate ${label}`}
                    </span>
                  )}
                </Button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
