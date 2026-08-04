"use client";

import { useCallback, useEffect, useState } from "react";
import { getComparisonBlocks } from "@/lib/api";
import type { ComparisonResult, DiffBlock } from "@/lib/types";

/** Matches the server's default page size, so offsets line up with its windows. */
const WINDOW_SIZE = 200;

export interface WindowedBlocks {
  blocks: DiffBlock[];
  totalBlocks: number;
  isComplete: boolean;
  isLoading: boolean;
  error: string | null;
  retry: () => void;
}

/**
 * Loads the rest of a windowed comparison.
 *
 * The server returns only the first window when a comparison is large,
 * flagging it with `truncated`. Rendering that window as though it were the
 * whole collation is the worst failure this application can have: the reader
 * sees a complete-looking comparison silently missing most of its text, under
 * a summary bar reporting metrics for blocks that are not on the page.
 *
 * ## Why everything is loaded rather than only what is scrolled to
 *
 * The obvious design fetches a window when the virtualizer approaches it. That
 * is right for scrolling and wrong for everything else: "next change" cannot
 * know where the next change is, the change count is a count within the loaded
 * window, and a shared `?block=2500` link points at a block that does not
 * exist yet. Those are whole-comparison questions, so the whole comparison has
 * to arrive. Windowing keeps any single response small, which is what it was
 * for; it was never a promise that the reader only ever wants the first two
 * hundred blocks.
 *
 * One window is fetched per pass, and appending re-runs this effect to fetch
 * the next. Sequencing then needs no reasoning about interleaved responses,
 * and opening a long manuscript cannot burst requests at its own rate limiter.
 *
 * This hook does not contradict the route fetching on the server: the first
 * payload still arrives with the HTML, which is what makes an unknown
 * comparison a real 404. Only the continuation is client-side.
 */
export function useWindowedBlocks(comparison: ComparisonResult): WindowedBlocks {
  const [blocks, setBlocks] = useState<DiffBlock[]>(comparison.blocks);
  const [error, setError] = useState<string | null>(null);

  const comparisonId = comparison.comparison_id;
  const truncated = comparison.truncated;
  const totalBlocks = truncated ? comparison.total_blocks : comparison.blocks.length;
  const loaded = blocks.length;
  const isComplete = loaded >= totalBlocks;

  useEffect(() => {
    if (!truncated || isComplete || error !== null) {
      return;
    }

    let cancelled = false;

    getComparisonBlocks(comparisonId, loaded, WINDOW_SIZE)
      .then((page) => {
        if (cancelled) {
          return;
        }
        if (page.blocks.length === 0) {
          // The server has no more to give. Stopping keeps a bad offset from
          // spinning forever against the API.
          setError(
            "The server stopped returning blocks before the comparison was complete.",
          );
          return;
        }
        // Guarded by the offset it was requested at, so a late response from a
        // superseded render cannot append the same window twice.
        setBlocks((current) =>
          current.length === loaded ? [...current, ...page.blocks] : current,
        );
      })
      .catch((cause: unknown) => {
        if (cancelled) {
          return;
        }
        setError(
          cause instanceof Error
            ? cause.message
            : "Could not load the rest of this comparison.",
        );
      });

    return () => {
      cancelled = true;
    };
  }, [comparisonId, truncated, isComplete, error, loaded]);

  const retry = useCallback(() => setError(null), []);

  return {
    blocks,
    totalBlocks,
    isComplete,
    isLoading: !isComplete && error === null,
    error,
    retry,
  };
}
