"use client";

import { getComparison } from "@/lib/api";

/** Bounds on the poll interval, in milliseconds. */
const MIN_INTERVAL_MS = 500;
const MAX_INTERVAL_MS = 8_000;

/** Give up rather than poll a comparison that will never arrive. */
export const MAX_POLL_MS = 10 * 60 * 1000;

function jittered(interval: number): number {
  // Full jitter. Several researchers submitting large manuscripts at once
  // would otherwise poll in lockstep and arrive as a burst.
  return interval / 2 + Math.random() * (interval / 2);
}

export interface PollProgress {
  attempt: number;
  elapsedMs: number;
}

/**
 * Wait for a comparison the server accepted but has not finished.
 *
 * A comparison above the inline budget returns `202` and is computed in the
 * background. Something has to wait for it, and doing so here means the
 * researcher waits on the page they are already looking at rather than being
 * sent to a comparison that does not exist yet.
 *
 * Backoff is exponential and bounded, with full jitter. The first retry is
 * quick because most accepted comparisons finish quickly; the ceiling keeps a
 * genuinely long collation from being polled hundreds of times.
 */
export async function waitForComparison(
  comparisonId: string,
  {
    initialDelayMs,
    onProgress,
    signal,
    now = () => Date.now(),
    sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms)),
  }: {
    initialDelayMs?: number;
    onProgress?: (progress: PollProgress) => void;
    signal?: AbortSignal;
    now?: () => number;
    sleep?: (ms: number) => Promise<void>;
  } = {},
): Promise<void> {
  const started = now();
  let interval = Math.min(
    Math.max(initialDelayMs ?? MIN_INTERVAL_MS, MIN_INTERVAL_MS),
    MAX_INTERVAL_MS,
  );
  let attempt = 0;

  for (;;) {
    if (signal?.aborted) {
      return;
    }

    const elapsedMs = now() - started;
    if (elapsedMs > MAX_POLL_MS) {
      throw new Error(
        "This comparison is taking longer than expected. It may still finish — the link will work once it does.",
      );
    }

    attempt += 1;
    onProgress?.({ attempt, elapsedMs });

    await sleep(jittered(interval));
    if (signal?.aborted) {
      return;
    }

    // A terminal failure surfaces as an ApiError and is deliberately not
    // caught here: polling past a comparison the server has given up on would
    // leave the researcher watching a spinner forever.
    const outcome = await getComparison(comparisonId, false);
    if (outcome.status === "COMPLETE") {
      return;
    }

    interval = Math.min(interval * 2, MAX_INTERVAL_MS);
  }
}
