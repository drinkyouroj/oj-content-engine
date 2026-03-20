/**
 * components/score-breakdown.tsx — Score dimension visualization for a scored trend.
 *
 * Implements PRD Section 3 (Topic Triage Rubric). Renders six horizontal bar rows,
 * one per scoring dimension, colour-coded by threshold: green ≥65, yellow 55-64,
 * red <55.
 *
 * Inputs:  breakdown — Record<string, number> from score_breakdown JSONB column.
 *          Values are 0-100 per dimension.
 * Outputs: Stack of labelled progress bars with score numerals.
 */

interface Dimension {
  key: string;
  label: string;
  weight: string;
}

const DIMENSIONS: readonly Dimension[] = [
  { key: "signal_strength", label: "Signal Strength", weight: "25%" },
  { key: "brand_angle_availability", label: "Brand Angle", weight: "20%" },
  { key: "timing_window", label: "Timing Window", weight: "15%" },
  { key: "depth_potential", label: "Depth Potential", weight: "15%" },
  { key: "novelty", label: "Novelty", weight: "15%" },
  { key: "community_resonance", label: "Community Resonance", weight: "10%" },
] as const;

interface ScoreBreakdownProps {
  breakdown: Record<string, number>;
}

/**
 * Returns the Tailwind fill colour class for a given dimension score.
 *
 * @param score  0-100 dimension score
 * @returns Tailwind bg-* class string
 */
function barColour(score: number): string {
  if (score >= 65) return "bg-green-500";
  if (score >= 55) return "bg-yellow-500";
  return "bg-red-500";
}

/**
 * Horizontal bar breakdown of all six triage rubric dimensions.
 * Rendered as a Server Component — no client-side JS required.
 *
 * @param breakdown  Map of dimension key → 0-100 score from score_breakdown JSONB
 */
export function ScoreBreakdown({ breakdown }: ScoreBreakdownProps) {
  return (
    <div className="space-y-3">
      {DIMENSIONS.map(({ key, label, weight }) => {
        const score = breakdown[key] ?? 0;
        const clampedScore = Math.min(100, Math.max(0, score));

        return (
          <div key={key}>
            {/* Label row */}
            <div className="mb-1 flex items-center justify-between">
              <span className="text-sm text-zinc-300">
                {label}
                <span className="ml-1 text-xs text-zinc-600">{weight}</span>
              </span>
              <span className="font-mono text-sm text-zinc-200">{clampedScore}</span>
            </div>

            {/* Track + fill */}
            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
              <div
                className={`h-full rounded-full transition-all ${barColour(clampedScore)}`}
                style={{ width: `${clampedScore}%` }}
                role="meter"
                aria-label={label}
                aria-valuenow={clampedScore}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
