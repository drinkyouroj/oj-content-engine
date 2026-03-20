"use client";

/**
 * components/thesis-input.tsx — Client Component for viewing and editing topic thesis.
 *
 * Implements PRD Section 5 (Approval UI). Allows the reviewer to set or update the
 * thesis (the human-authored angle) for a topic before approving content generation.
 *
 * States:
 *  - No thesis provided: textarea + "Save Thesis" button.
 *  - Submitting: button shows loading indicator, textarea is disabled.
 *  - Thesis saved: read-only block with "Edit" toggle.
 *  - Edit mode: textarea pre-filled with existing thesis.
 *
 * After a successful save, calls router.refresh() so upstream Server Components
 * re-fetch the updated topic row from Postgres.
 *
 * Inputs:  topicId (UUID), thesis (string | null), thesisProvided (boolean)
 * Outputs: POST /api/thesis → { topicId, thesis }
 */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ThesisInputProps {
  topicId: string;
  thesis: string | null;
  thesisProvided: boolean;
}

/**
 * Interactive thesis editor for a single topic.
 * Uses useTransition to track in-flight POST state without a separate boolean.
 *
 * @param topicId         UUID of the parent topic row
 * @param thesis          Current thesis string, or null if not yet set
 * @param thesisProvided  Whether the topic already has a saved thesis
 */
export function ThesisInput({ topicId, thesis, thesisProvided }: ThesisInputProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  // Local draft value in the textarea
  const [draft, setDraft] = useState<string>(thesis ?? "");
  // Controls whether we are in edit/input mode vs read-only mode
  const [isEditing, setIsEditing] = useState<boolean>(!thesisProvided);
  // Stores any error message from a failed save
  const [error, setError] = useState<string | null>(null);
  // Suggested theses returned by the suggest API
  const [suggestions, setSuggestions] = useState<string[]>([]);
  // Loading state for the suggest API call
  const [loadingSuggestions, setLoadingSuggestions] = useState<boolean>(false);
  // Error from the suggest API
  const [suggestError, setSuggestError] = useState<string | null>(null);

  /**
   * POSTs the current draft to /api/thesis and switches to read-only mode on success.
   */
  function handleSave() {
    if (!draft.trim()) return;
    setError(null);

    startTransition(async () => {
      try {
        const res = await fetch("/api/thesis", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topicId, thesis: draft.trim() }),
        });

        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as { error?: string };
          setError(body.error ?? `Save failed (${res.status})`);
          return;
        }

        setIsEditing(false);
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unexpected error");
      }
    });
  }

  /**
   * Calls POST /api/suggest-theses to generate thesis angle suggestions for the topic.
   * Populates the suggestions array on success, or shows an error on failure.
   */
  async function handleSuggestTheses() {
    setSuggestError(null);
    setLoadingSuggestions(true);

    try {
      const res = await fetch("/api/suggest-theses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topicId }),
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setSuggestError(body.error ?? `Suggestion failed (${res.status})`);
        return;
      }

      const data = (await res.json()) as { theses: string[] };
      setSuggestions(data.theses);
    } catch (err) {
      setSuggestError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoadingSuggestions(false);
    }
  }

  /** Switches back to edit mode, pre-filling the textarea with the current thesis. */
  function handleEdit() {
    setDraft(thesis ?? draft);
    setIsEditing(true);
    setError(null);
  }

  // ----- Read-only view -----
  if (!isEditing) {
    return (
      <div className="space-y-2">
        <div className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
            {draft || thesis || "—"}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleEdit}
          className="border-zinc-700 text-zinc-400 hover:text-zinc-200"
        >
          Edit
        </Button>
      </div>
    );
  }

  // ----- Edit / input view -----
  return (
    <div className="space-y-2">
      <Textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="What's the unique angle here? One sentence is enough."
        disabled={isPending}
        className="min-h-24 resize-none border-zinc-700 bg-zinc-800 text-sm text-zinc-200 placeholder:text-zinc-600 focus-visible:border-[#00B4D8] focus-visible:ring-[#00B4D8]/30"
      />

      {error && (
        <p className="text-xs text-red-400" role="alert">
          {error}
        </p>
      )}

      {/* Thesis suggestion cards */}
      {suggestions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-zinc-500">Suggested angles:</p>
          {suggestions.map((suggestion, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => setDraft(suggestion)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-3 text-left text-sm text-zinc-300 transition-colors hover:border-[#00B4D8] hover:bg-zinc-800/80 cursor-pointer"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button
          onClick={handleSave}
          disabled={isPending || !draft.trim()}
          size="sm"
          className="bg-[#00B4D8] text-zinc-900 hover:bg-[#00B4D8]/90 disabled:opacity-50"
        >
          {isPending ? (
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-zinc-900 border-t-transparent" />
              Saving…
            </span>
          ) : (
            "Save Thesis"
          )}
        </Button>

        {/* Allow cancelling back to read-only only if a thesis already existed */}
        {thesisProvided && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsEditing(false)}
            disabled={isPending}
            className="text-zinc-500 hover:text-zinc-300"
          >
            Cancel
          </Button>
        )}

        <Button
          variant="outline"
          size="sm"
          onClick={handleSuggestTheses}
          disabled={loadingSuggestions || isPending}
          className="border-[#00B4D8]/50 text-[#00B4D8] hover:bg-[#00B4D8]/10 hover:text-[#00B4D8] disabled:opacity-50"
        >
          {loadingSuggestions ? (
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[#00B4D8] border-t-transparent" />
              Generating…
            </span>
          ) : suggestions.length > 0 ? (
            "New Suggestions"
          ) : (
            "Suggest Theses"
          )}
        </Button>

        {suggestError && (
          <p className="text-xs text-red-400" role="alert">
            {suggestError}
          </p>
        )}
      </div>
    </div>
  );
}
