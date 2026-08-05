"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { waitForComparison } from "@/lib/waitForComparison";

/**
 * A comparison the server has accepted but not finished.
 *
 * Reachable by sharing or refreshing `/c/{id}` while a large collation is
 * still running. The route cannot render a comparison that has no blocks yet,
 * and rendering one anyway is how this path used to end at a 500 page.
 *
 * The wait happens here rather than on the server: holding the response open
 * for minutes would give the reader a blank tab and no way to tell a slow
 * collation from a hung one.
 */
export function ComparisonPending({
  comparisonId,
  retryAfter,
}: {
  comparisonId: string;
  retryAfter: number;
}) {
  const router = useRouter();
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    waitForComparison(comparisonId, {
      initialDelayMs: retryAfter * 1000,
      signal: controller.signal,
    })
      .then(() => {
        if (!controller.signal.aborted) {
          // Re-run the server component, which now finds a finished
          // comparison and renders it.
          router.refresh();
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setFailure(
          error instanceof Error
            ? error.message
            : "This comparison could not be loaded.",
        );
      });

    return () => controller.abort();
  }, [comparisonId, retryAfter, router]);

  return (
    <div
      className="mx-auto max-w-prose py-24 text-center font-ui"
      data-testid="comparison-pending"
      data-state={failure === null ? "waiting" : "failed"}
    >
      {failure === null ? (
        <>
          <h1 className="mb-3 font-manuscript text-2xl text-ink">Still collating</h1>
          <p className="text-sm text-ink-muted" aria-live="polite">
            These manuscripts are long enough that the comparison is being
            prepared in the background. This page will show it as soon as it is
            ready; the link keeps working either way.
          </p>
        </>
      ) : (
        <>
          <h1 className="mb-3 font-manuscript text-2xl text-ink">
            This comparison is not ready
          </h1>
          <p className="text-sm text-ink-muted" role="alert">
            {failure}
          </p>
        </>
      )}
    </div>
  );
}
