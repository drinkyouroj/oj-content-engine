/**
 * app/dashboard/research/page.tsx — Steered topic research page (Server Component).
 *
 * Implements PRD Section 3 (Steered Topic Discovery). Renders the research
 * interface where users can search for articles across multiple sources
 * (RSS, Reddit, HN, Twitter, web) and create topics from selected results.
 *
 * Data flow:
 *   User query → POST /api/research → Worker research endpoint
 *   Selected articles → POST /api/create-topics → Worker create-topics endpoint
 *   Created topics appear on /dashboard
 */

// Force dynamic rendering — this page makes client-side API calls
// and must not be statically prerendered at build time.
export const dynamic = "force-dynamic";

import { ResearchResults } from "@/components/research-results";
import Link from "next/link";

/**
 * Research page for steered topic discovery.
 * Wraps the ResearchResults client component in a layout with
 * navigation back to the main dashboard.
 *
 * @returns Research page with search interface and results
 */
export default function ResearchPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link
        href="/dashboard"
        className="text-sm text-zinc-500 hover:text-zinc-300"
      >
        &larr; Back to dashboard
      </Link>
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Research Topics</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Search for articles to seed your content pipeline. Selected articles
          become topics on your dashboard, ready for thesis and generation.
        </p>
      </div>
      <ResearchResults />
    </div>
  );
}
