"use client";

export interface ChangeNavigatorProps {
  activeChangedPosition: number | null;
  activeBlockIndex: number | null;
  totalChanges: number;
  /** True while the comparison is still loading windows, so the count is a
   *  count of what has arrived rather than of the whole collation. */
  partial?: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onClear?: () => void;
  className?: string;
  disabled?: boolean;
}

function statusText(
  activeChangedPosition: number | null,
  activeBlockIndex: number | null,
  totalChanges: number,
  partial: boolean,
) {
  // "so far" rather than a bare number: a count that will grow must not be
  // read as a finding about the text.
  const total = partial ? `${totalChanges} so far` : `${totalChanges}`;

  if (totalChanges === 0) {
    return partial ? "No changed blocks loaded yet" : "No changed blocks";
  }

  if (activeChangedPosition === null) {
    return activeBlockIndex === null
      ? `${total} changed blocks`
      : `Block ${activeBlockIndex} selected`;
  }

  return `Change ${activeChangedPosition + 1} of ${total}`;
}

export function ChangeNavigator({
  activeChangedPosition,
  activeBlockIndex,
  totalChanges,
  partial = false,
  onPrevious,
  onNext,
  onClear,
  className = "",
  disabled = false,
}: ChangeNavigatorProps) {
  const controlsDisabled = disabled || totalChanges === 0;
  const label = statusText(activeChangedPosition, activeBlockIndex, totalChanges, partial);

  return (
    <nav
      aria-label="Changed block navigation"
      className={`change-navigator border border-rule bg-paper p-3 font-ui text-sm text-ink ${className}`}
      data-testid="change-navigator"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span aria-live="polite" className="font-semibold text-ink" data-testid="change-position">
          {label}
        </span>
        <button
          type="button"
          onClick={onPrevious}
          disabled={controlsDisabled}
          className="border border-rule px-3 py-1.5 text-ink transition-colors hover:border-rubric hover:text-rubric focus:outline-none focus:ring-2 focus:ring-rubric focus:ring-offset-2 focus:ring-offset-paper disabled:cursor-not-allowed disabled:border-rule disabled:text-ink-muted motion-reduce:transition-none"
          aria-label="Go to previous changed block (k or p)"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={controlsDisabled}
          className="border border-rule px-3 py-1.5 text-ink transition-colors hover:border-rubric hover:text-rubric focus:outline-none focus:ring-2 focus:ring-rubric focus:ring-offset-2 focus:ring-offset-paper disabled:cursor-not-allowed disabled:border-rule disabled:text-ink-muted motion-reduce:transition-none"
          aria-label="Go to next changed block (j or n)"
        >
          Next
        </button>
        {onClear ? (
          <button
            type="button"
            onClick={onClear}
            disabled={disabled || activeBlockIndex === null}
            className="border border-rule px-3 py-1.5 text-ink transition-colors hover:border-rubric hover:text-rubric focus:outline-none focus:ring-2 focus:ring-rubric focus:ring-offset-2 focus:ring-offset-paper disabled:cursor-not-allowed disabled:border-rule disabled:text-ink-muted motion-reduce:transition-none"
            aria-label="Clear the active block (Escape)"
          >
            Clear
          </button>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        Keyboard: <kbd>j</kbd> or <kbd>n</kbd> next, <kbd>k</kbd> or <kbd>p</kbd>{" "}
        previous, <kbd>Esc</kbd> clear.
      </p>
    </nav>
  );
}
