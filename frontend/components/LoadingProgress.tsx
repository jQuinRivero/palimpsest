"use client";

/**
 * Honest reporting of a partially loaded comparison.
 *
 * A long comparison arrives one window at a time. Until it is whole, the
 * change count is a count of what has loaded and the summary metrics describe
 * blocks that are not yet on the page. Saying so is not an implementation
 * detail leaking into the interface: a reader drawing conclusions about a text
 * needs to know whether they are looking at all of it.
 */
export function LoadingProgress({
  loadedBlocks,
  totalBlocks,
  isComplete,
  error,
  onRetry,
}: {
  loadedBlocks: number;
  totalBlocks: number;
  isComplete: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (error !== null) {
    return (
      <div
        className="mb-4 border border-deletion bg-paper p-3 font-ui text-sm text-ink"
        data-testid="block-loading-status"
        data-state="error"
        role="alert"
      >
        <p>
          Only {loadedBlocks.toLocaleString()} of {totalBlocks.toLocaleString()} blocks
          could be loaded, so this comparison is incomplete. {error}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 border border-rule px-3 py-1.5 text-ink transition-colors hover:border-rubric hover:text-rubric focus:outline-none focus:ring-2 focus:ring-rubric focus:ring-offset-2 focus:ring-offset-paper motion-reduce:transition-none"
        >
          Try again
        </button>
      </div>
    );
  }

  if (isComplete) {
    // Announced once so a screen-reader user learns the earlier partial counts
    // can now be trusted, then rendered as nothing visible.
    return (
      <div
        className="sr-only"
        data-testid="block-loading-status"
        data-state="complete"
        aria-live="polite"
      >
        All {totalBlocks.toLocaleString()} blocks loaded.
      </div>
    );
  }

  return (
    <div
      className="mb-4 border border-rule bg-vellum p-3 font-ui text-sm text-ink-muted"
      data-testid="block-loading-status"
      data-state="loading"
      aria-live="polite"
    >
      Loading the full comparison — {loadedBlocks.toLocaleString()} of{" "}
      {totalBlocks.toLocaleString()} blocks. Counts and metrics describe the whole
      comparison; navigation reaches only what has loaded.
    </div>
  );
}
