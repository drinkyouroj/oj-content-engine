"use client";

/**
 * components/research-results.tsx — Client Component for steered topic research.
 *
 * Implements PRD Section 3 (Steered Topic Discovery). Provides a search interface
 * that queries the research API for articles, displays results as selectable cards,
 * and allows the user to create topics from selected articles.
 *
 * States:
 *  - Idle: search input with submit button.
 *  - Loading: spinner while search is in flight.
 *  - Results: cards with checkboxes for selection, "Create N Topics" action.
 *  - Creating: spinner on the create button while topics are being created.
 *  - Success: confirmation message with link back to dashboard.
 *  - Error: red error text for search or creation failures.
 *
 * API calls:
 *  - POST /api/research → { results, warnings }
 *  - POST /api/create-topics → { created, skipped, topic_ids }
 */

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

/** Shape of a single article returned by the research API. */
interface ResearchArticle {
  title: string;
  url: string;
  source: string;
  body_preview: string;
  published_at: string | null;
}

/** Response shape from POST /api/research. */
interface SearchResponse {
  results: ResearchArticle[];
  warnings: string[];
}

/** Response shape from POST /api/create-topic (singular — synthesizes one topic from multiple articles). */
interface CreateResponse {
  topic_id: string;
  title: string;
  source_count: number;
}

/**
 * Renders a color-coded badge for the article source.
 *
 * @param source - Source identifier: rss, reddit, hn, twitter, or web
 * @returns Badge element with source-specific color scheme
 */
function SourceBadge({ source }: { source: string }) {
  const colors: Record<string, string> = {
    rss: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
    reddit: "bg-[#FF6B35]/20 text-[#FF6B35] border-[#FF6B35]/30",
    hn: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    twitter: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    web: "bg-[#00B4D8]/20 text-[#00B4D8] border-[#00B4D8]/30",
  };
  return (
    <Badge variant="outline" className={colors[source] || colors.web}>
      {source}
    </Badge>
  );
}

/**
 * Self-contained research results component.
 *
 * Manages the full search-select-create flow for steered topic research.
 * No props required — all state is managed internally.
 *
 * @returns Research interface with search, results, and topic creation
 */
export function ResearchResults() {
  const [query, setQuery] = useState<string>("");
  const [results, setResults] = useState<ResearchArticle[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<boolean>(false);
  const [creating, setCreating] = useState<boolean>(false);
  const [success, setSuccess] = useState<{ topic_id: string; title: string; source_count: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  /**
   * Searches for articles via POST /api/research.
   * Resets previous results, selection, and status states before fetching.
   */
  async function handleSearch() {
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setSuccess(null);
    setResults([]);
    setWarnings([]);
    setSelected(new Set());

    try {
      const res = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim() }),
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setError(body.error ?? `Search failed (${res.status})`);
        return;
      }

      const data = (await res.json()) as SearchResponse;
      setResults(data.results);
      setWarnings(data.warnings ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  /**
   * Toggles selection state for an article by URL.
   *
   * @param url - The article URL to toggle in the selection set
   */
  function toggleSelected(url: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) {
        next.delete(url);
      } else {
        next.add(url);
      }
      return next;
    });
  }

  /**
   * Creates one synthesized topic from all selected articles via POST /api/create-topic.
   * Multiple articles are combined into a single topic with source URLs preserved.
   */
  async function handleCreate() {
    const articles = results.filter((r) => selected.has(r.url));
    if (articles.length === 0) return;

    setCreating(true);
    setError(null);

    try {
      const res = await fetch("/api/create-topic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ articles }),
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setError(body.error ?? `Create failed (${res.status})`);
        return;
      }

      const data = (await res.json()) as CreateResponse;
      setSuccess(data);
      setResults([]);
      setSelected(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setCreating(false);
    }
  }

  /**
   * Truncates a string to the given max length, appending an ellipsis if needed.
   *
   * @param text - The string to truncate
   * @param max  - Maximum character length (default 200)
   * @returns Truncated string with trailing ellipsis, or original if within limit
   */
  function truncate(text: string, max = 200): string {
    if (text.length <= max) return text;
    return text.slice(0, max).trimEnd() + "\u2026";
  }

  /**
   * Truncates a URL for display, stripping protocol and trimming to 60 chars.
   *
   * @param url - Full URL string
   * @returns Shortened URL for display purposes
   */
  function displayUrl(url: string): string {
    const stripped = url.replace(/^https?:\/\//, "");
    if (stripped.length > 60) return stripped.slice(0, 57) + "\u2026";
    return stripped;
  }

  return (
    <div className="space-y-4">
      {/* Search input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSearch();
        }}
        className="flex gap-2"
      >
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for a topic, keyword, or URL..."
          disabled={loading}
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 placeholder:text-zinc-500 focus:border-[#00B4D8] focus:outline-none focus:ring-1 focus:ring-[#00B4D8]/30 disabled:opacity-50"
        />
        <Button
          type="submit"
          disabled={loading || !query.trim()}
          className="bg-[#00B4D8] text-zinc-900 hover:bg-[#00B4D8]/90 disabled:opacity-50"
        >
          {loading ? (
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-zinc-900 border-t-transparent" />
              Searching...
            </span>
          ) : (
            "Search"
          )}
        </Button>
      </form>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="space-y-1">
          {warnings.map((warning, idx) => (
            <p key={idx} className="text-xs text-amber-400">
              {warning}
            </p>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-sm text-red-400" role="alert">
          {error}
        </p>
      )}

      {/* Success */}
      {success && (
        <div className="rounded-lg border border-[#00B4D8]/30 bg-[#00B4D8]/10 px-4 py-3">
          <p className="text-sm text-[#00B4D8]">
            Created topic from {success.source_count} source{success.source_count !== 1 ? "s" : ""}: &ldquo;{success.title}&rdquo;.{" "}
            <Link
              href={`/dashboard/review/${success.topic_id}`}
              className="underline underline-offset-2 hover:text-[#00B4D8]/80"
            >
              Review topic
            </Link>
            {" | "}
            <Link
              href="/dashboard"
              className="underline underline-offset-2 hover:text-[#00B4D8]/80"
            >
              Back to dashboard
            </Link>
          </p>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          {results.map((article) => {
            const isSelected = selected.has(article.url);
            return (
              <button
                key={article.url}
                type="button"
                onClick={() => toggleSelected(article.url)}
                className={`w-full cursor-pointer rounded-lg border bg-zinc-900 p-4 text-left transition-colors ${
                  isSelected
                    ? "border-[#00B4D8] bg-[#00B4D8]/5"
                    : "border-zinc-800 hover:border-zinc-700"
                }`}
              >
                <div className="flex items-start gap-3">
                  {/* Checkbox indicator */}
                  <div
                    className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                      isSelected
                        ? "border-[#00B4D8] bg-[#00B4D8]"
                        : "border-zinc-600 bg-zinc-800"
                    }`}
                  >
                    {isSelected && (
                      <svg
                        className="h-3 w-3 text-zinc-900"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={3}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    )}
                  </div>

                  {/* Card content */}
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-zinc-100">
                        {article.title}
                      </h3>
                      <SourceBadge source={article.source} />
                    </div>

                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="block text-xs text-zinc-500 hover:text-[#00B4D8] hover:underline"
                    >
                      {displayUrl(article.url)}
                    </a>

                    {article.body_preview && (
                      <p className="text-xs leading-relaxed text-zinc-400">
                        {truncate(article.body_preview)}
                      </p>
                    )}

                    {article.published_at && (
                      <p className="text-xs text-zinc-600">
                        {new Date(article.published_at).toLocaleDateString("en-US", {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                        })}
                      </p>
                    )}
                  </div>
                </div>
              </button>
            );
          })}

          {/* Create topics button */}
          <div className="flex items-center justify-between border-t border-zinc-800 pt-4">
            <p className="text-sm text-zinc-500">
              {selected.size} of {results.length} selected
            </p>
            <Button
              onClick={handleCreate}
              disabled={selected.size === 0 || creating}
              className="bg-[#00B4D8] text-zinc-900 hover:bg-[#00B4D8]/90 disabled:opacity-50"
            >
              {creating ? (
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-zinc-900 border-t-transparent" />
                  Creating...
                </span>
              ) : (
                `Create Topic (${selected.size} source${selected.size !== 1 ? "s" : ""})`
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Empty state after search */}
      {!loading && results.length === 0 && !success && !error && query && (
        <p className="py-8 text-center text-sm text-zinc-500">
          No results yet. Press Search to find articles.
        </p>
      )}
    </div>
  );
}
