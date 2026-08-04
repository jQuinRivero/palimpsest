import { notFound } from "next/navigation";
import { ApiError, getComparison } from "@/lib/api";
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

  let comparison;
  try {
    comparison = await getComparison(comparisonId);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 410)) {
      // An expired comparison is genuinely gone: sessions are a cache with a
      // deadline, not a system of record.
      notFound();
    }
    throw error;
  }

  const mode: ViewMode = view === "unified" ? "unified" : "synoptic";
  const requested = block !== undefined && /^\d+$/.test(block) ? Number(block) : null;
  const initialBlockIndex =
    requested !== null && requested < comparison.blocks.length ? requested : null;

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <DiffViewer
        comparison={comparison}
        initialMode={mode}
        initialBlockIndex={initialBlockIndex}
      />
    </main>
  );
}
