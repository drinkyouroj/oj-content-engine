/**
 * components/draft-preview.tsx — Platform-specific content draft renderer.
 *
 * Implements PRD Section 5 (Approval UI). Parses and displays generated draft content
 * differently depending on the target platform: Substack (article), Twitter/X (thread),
 * LinkedIn (post), and Instagram (caption + image card prompt).
 *
 * Inputs:  content, platform, modelUsed, notionPageId, generationMetadata from
 *          content_drafts table.
 * Outputs: Formatted content block + metadata footer.
 */

interface DraftPreviewProps {
  content: string;
  platform: string;
  modelUsed?: string | null;
  notionPageId?: string | null;
  generationMetadata?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Substack renderer
// ---------------------------------------------------------------------------

/**
 * Renders a Substack article draft.
 * Parses headings (#/##/###), [IMAGE: ...] markers, and a trailing FOOTNOTES: block.
 *
 * @param content Raw Substack draft string
 */
function SubstackContent({ content }: { content: string }) {
  // Split off footnotes section if present
  const footnoteSplit = content.split(/^FOOTNOTES:/m);
  const body = footnoteSplit[0];
  const footnotes = footnoteSplit[1] ?? null;

  const paragraphs = body.split(/\n\n/).filter(Boolean);

  return (
    <div className="space-y-4">
      {paragraphs.map((para, idx) => {
        const trimmed = para.trim();

        // Heading detection
        if (trimmed.startsWith("### ")) {
          return (
            <h3 key={idx} className="text-base font-semibold text-zinc-100">
              {trimmed.slice(4)}
            </h3>
          );
        }
        if (trimmed.startsWith("## ")) {
          return (
            <h2 key={idx} className="text-lg font-semibold text-zinc-100">
              {trimmed.slice(3)}
            </h2>
          );
        }
        if (trimmed.startsWith("# ")) {
          return (
            <h1 key={idx} className="text-xl font-bold text-zinc-100">
              {trimmed.slice(2)}
            </h1>
          );
        }

        // Image marker detection: [IMAGE: description]
        // Note: dotAll flag unavailable at ES2017 target; use [\s\S] instead.
        const imageMatch = trimmed.match(/^\[IMAGE:\s*([\s\S]*?)\]$/);
        if (imageMatch) {
          return (
            <div
              key={idx}
              className="rounded-md border-l-4 border-[#00B4D8] bg-zinc-800 px-4 py-3"
            >
              <p className="text-xs font-medium uppercase tracking-wide text-[#00B4D8]">
                Image prompt
              </p>
              <p className="mt-1 text-sm text-zinc-300">{imageMatch[1]}</p>
            </div>
          );
        }

        return (
          <p key={idx} className="text-sm leading-relaxed text-zinc-300">
            {trimmed}
          </p>
        );
      })}

      {footnotes && (
        <div className="mt-6 border-t border-zinc-800 pt-4">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500">
            Footnotes
          </p>
          <p className="whitespace-pre-line text-xs text-zinc-500">{footnotes.trim()}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Twitter renderer
// ---------------------------------------------------------------------------

/**
 * Renders a Twitter/X thread draft.
 * Splits on [TWEET] prefix; shows character-count badge (red when >280).
 *
 * @param content Raw Twitter draft string
 */
function TwitterContent({ content }: { content: string }) {
  // Tweets are separated by "[TWEET]" prefix markers
  const rawTweets = content.split(/\[TWEET\]/);
  const tweets = rawTweets.map((t) => t.trim()).filter(Boolean);

  if (tweets.length === 0) {
    return <p className="text-sm text-zinc-400">No tweets parsed.</p>;
  }

  return (
    <div className="space-y-3">
      {tweets.map((tweet, idx) => {
        const charCount = tweet.length;
        const overLimit = charCount > 280;
        return (
          <div key={idx} className="relative rounded-lg bg-zinc-800 p-4">
            <p className="pr-14 text-sm leading-relaxed text-zinc-200">{tweet}</p>
            <span
              className={`absolute right-3 top-3 rounded-full px-2 py-0.5 font-mono text-xs ${
                overLimit
                  ? "bg-red-500/20 text-red-400"
                  : "bg-zinc-700 text-zinc-400"
              }`}
            >
              {charCount}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LinkedIn renderer
// ---------------------------------------------------------------------------

/**
 * Renders a LinkedIn post draft as formatted paragraphs.
 *
 * @param content Raw LinkedIn draft string
 */
function LinkedInContent({ content }: { content: string }) {
  const paragraphs = content.split(/\n\n/).filter(Boolean);
  return (
    <div className="space-y-3">
      {paragraphs.map((para, idx) => (
        <p key={idx} className="text-sm leading-relaxed text-zinc-300">
          {para.trim()}
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Instagram renderer
// ---------------------------------------------------------------------------

/**
 * Renders an Instagram draft: caption + image card prompt split on ---IMAGE CARD---.
 *
 * @param content Raw Instagram draft string
 */
function InstagramContent({ content }: { content: string }) {
  const [caption, imageCard] = content.split("---IMAGE CARD---");

  return (
    <div className="space-y-4">
      {caption && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
            Caption
          </p>
          <p className="whitespace-pre-line text-sm leading-relaxed text-zinc-300">
            {caption.trim()}
          </p>
        </div>
      )}

      {imageCard && (
        <div className="rounded-md border-l-4 border-[#00B4D8] bg-zinc-800/60 px-4 py-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-[#00B4D8]">
            Image card prompt
          </p>
          <p className="whitespace-pre-line text-sm text-zinc-300">{imageCard.trim()}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metadata badges
// ---------------------------------------------------------------------------

interface GenerationFlag {
  key: string;
  label: string;
}

const GENERATION_FLAGS: readonly GenerationFlag[] = [
  { key: "ai_originated", label: "AI-originated" },
  { key: "voice_drift_applied", label: "Voice-drift applied" },
  { key: "no_exemplars", label: "No exemplars" },
] as const;

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Renders a content draft with platform-appropriate formatting plus a metadata footer.
 * Supports substack, twitter, linkedin, and instagram platforms.
 *
 * @param content              Raw draft body text
 * @param platform             Platform slug (substack | twitter | linkedin | instagram)
 * @param modelUsed            LLM model identifier, shown as a mono badge
 * @param notionPageId         Notion page UUID — renders an "Open in Notion" link if present
 * @param generationMetadata   Arbitrary generation flags persisted as JSONB
 */
export function DraftPreview({
  content,
  platform,
  modelUsed,
  notionPageId,
  generationMetadata,
}: DraftPreviewProps) {
  const platformKey = platform.toLowerCase();

  const activeFlags = GENERATION_FLAGS.filter(
    ({ key }) => generationMetadata?.[key] === true
  );

  return (
    <div className="space-y-4">
      {/* Platform content */}
      <div>
        {platformKey === "substack" && <SubstackContent content={content} />}
        {platformKey === "twitter" && <TwitterContent content={content} />}
        {platformKey === "linkedin" && <LinkedInContent content={content} />}
        {platformKey === "instagram" && <InstagramContent content={content} />}
        {!["substack", "twitter", "linkedin", "instagram"].includes(platformKey) && (
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
            {content}
          </p>
        )}
      </div>

      {/* Metadata footer */}
      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-3">
        {modelUsed && (
          <span className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-xs text-zinc-500">
            {modelUsed}
          </span>
        )}

        {notionPageId && (
          <a
            href={`https://notion.so/${notionPageId.replace(/-/g, "")}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[#00B4D8] hover:underline"
          >
            Open in Notion ↗
          </a>
        )}

        {activeFlags.map(({ key, label }) => (
          <span
            key={key}
            className="rounded border border-zinc-700 px-2 py-0.5 text-xs text-zinc-500"
          >
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
