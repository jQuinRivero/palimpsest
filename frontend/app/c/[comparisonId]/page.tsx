import { notFound } from "next/navigation";
import { ApiError, getComparison } from "@/lib/api";
import { ComparisonPending } from "@/components/ComparisonPending";
import { DiffViewer } from "@/components/DiffViewer";
import type { ViewMode } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * The comparison reading route.
 *
 * The payload is fetched in a server component: first paint arrives with the
 * text already in it, there is no client waterfall, and the API origin stays
 * off the browser. Interaction lives in `DiffViewer`, which is a client
 * component.
 */
export default async function ComparisonPage({
  params,
  searchParams,
}: {
  params: Promise<{ comparisonId: string }>;
  searchParams: Promise<{ view?: string; block?: string }>;
}) {
  const { comparisonId } = await params;
  const { view, block } = await searchParams;

  let outcome;
  try {
    outcome = await getComparison(comparisonId);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 410)) {
      // An expired comparison is genuinely gone: sessions are a cache with a
      // deadline, not a system of record.
      notFound();
    }
    throw error;
  }

  if (outcome.status === "PENDING") {
    // Accepted but not finished — reachable by sharing or refreshing the link
    // while a large collation runs. There is no comparison to render yet, and
    // rendering one anyway is how this path used to return a 500.
    return (
      <main className="mx-auto max-w-7xl px-6 py-10">
        <ComparisonPending
          comparisonId={comparisonId}
          retryAfter={outcome.accepted.retry_after}
        />
      </main>
    );
  }

  const comparison = outcome.comparison;

  const mode: ViewMode = view === "unified" ? "unified" : "synoptic";
  const requested = block !== undefined && /^\d+$/.test(block) ? Number(block) : null;
  // Bounded by the whole comparison, not by the first window. A large
  // comparison arrives truncated, so clamping against `blocks.length` would
  // silently drop any shared link pointing past the first window — exactly
  // the links most worth sharing in a long manuscript.
  const initialBlockIndex =
    requested !== null && requested < comparison.total_blocks ? requested : null;

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <DiffViewer
        // Keyed so that navigating from one comparison to another builds a
        // fresh viewer rather than carrying the previous comparison's loaded
        // blocks into the new one.
        key={comparison.comparison_id}
        comparison={comparison}
        initialMode={mode}
        initialBlockIndex={initialBlockIndex}
      />
    </main>
  );
}
