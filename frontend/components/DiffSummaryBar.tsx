import type { DiffMetrics } from "@/lib/types";

/**
 * Percentage for display.
 *
 * Rounding is not safe at the top of the range. A 136,000-word novel with 883
 * changed words scores 0.9967, which rounds to "100% similar" — telling a
 * reader that a manuscript with hundreds of revisions is untouched. Short
 * witnesses never expose this, because one edit moves their score by whole
 * points, so it only appears on exactly the long texts this tool is for.
 *
 * Only a comparison with no wording changes at all may claim 100%.
 */
function percent(value: number, unchanged: boolean): string {
  const scaled = unchanged ? Math.round(value * 100) : Math.min(99, Math.floor(value * 100));
  return `${scaled}%`;
}

function plural(count: number, noun: string): string {
  return `${count.toLocaleString()} ${noun}${count === 1 ? "" : "s"}`;
}

/**
 * Persistent chrome summarising the collation.
 *
 * Every number here comes from the payload. The client never computes a
 * metric: `insertions` and friends are counts of *words*, while a payload
 * `Token` carries a contiguous run of them, so counting array entries would
 * silently produce a different and wrong number.
 */
export function DiffSummaryBar({ metrics }: { metrics: DiffMetrics }) {
  const unchanged = metrics.edit_count === 0;
  const structural =
    metrics.blocks_moved +
    metrics.blocks_split +
    metrics.blocks_merged +
    metrics.stanza_breaks_changed;

  return (
    <div
      className="flex flex-wrap items-baseline gap-x-6 gap-y-2 border-b border-rule pb-3 font-ui text-sm text-ink-muted"
      data-testid="diff-summary-bar"
      aria-label="Comparison summary"
    >
      <span className="text-ink">
        <span className="font-mono tabular-nums">{percent(metrics.similarity, unchanged)}</span>{" "}
        similar
      </span>

      {unchanged ? (
        <span>No wording changes</span>
      ) : (
        <>
          <span className="text-addition">
            +{plural(metrics.insertions, "word")}
          </span>
          <span className="text-deletion">
            −{plural(metrics.deletions, "word")}
          </span>
        </>
      )}

      {structural > 0 && (
        <span className="text-moved">
          {[
            metrics.blocks_moved && plural(metrics.blocks_moved, "block") + " moved",
            metrics.blocks_split && plural(metrics.blocks_split, "block") + " split",
            metrics.blocks_merged && plural(metrics.blocks_merged, "block") + " merged",
            // A stanza break changes no words at all, so without this line a
            // poem re-divided between drafts reads as "No wording changes"
            // and nothing else.
            metrics.stanza_breaks_changed &&
              plural(metrics.stanza_breaks_changed, "stanza break") + " changed",
          ]
            .filter(Boolean)
            .join(", ")}
        </span>
      )}

      <span className="ml-auto font-mono text-xs tabular-nums text-ink-muted">
        {metrics.a_word_count.toLocaleString()} → {metrics.b_word_count.toLocaleString()} words
      </span>
    </div>
  );
}
