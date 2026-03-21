"use client";

/**
 * components/auto-refresh.tsx — Auto-refreshes the page while a topic is generating.
 *
 * Polls the current page every 5 seconds using router.refresh() when the topic
 * status is "generating". Stops polling once the status changes. Shows a subtle
 * indicator so the user knows the page is waiting for generation to complete.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

interface AutoRefreshProps {
  /** Current topic status from the server. */
  status: string;
  /** Polling interval in milliseconds. Defaults to 5000 (5s). */
  intervalMs?: number;
}

/**
 * Renders a "Generating..." indicator and auto-refreshes the page
 * while the topic status is "generating".
 */
export function AutoRefresh({ status, intervalMs = 5000 }: AutoRefreshProps) {
  const router = useRouter();

  useEffect(() => {
    if (status !== "generating") return;

    const interval = setInterval(() => {
      router.refresh();
    }, intervalMs);

    return () => clearInterval(interval);
  }, [status, intervalMs, router]);

  if (status !== "generating") return null;

  return (
    <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2">
      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
      <p className="text-sm text-amber-400">
        Generating content... This page will update automatically.
      </p>
    </div>
  );
}
