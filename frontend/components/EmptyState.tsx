"use client";

export interface EmptyStateProps {
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({
  title,
  message,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  return (
    <div className="rounded-2xl border border-dashed border-rule bg-vellum/45 px-6 py-8 text-center font-ui">
      <h2 className="font-manuscript text-2xl text-ink">{title}</h2>
      <p className="mx-auto mt-3 max-w-prose text-sm leading-6 text-ink-muted">
        {message}
      </p>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="mt-5 rounded-full border border-rule px-4 py-2 text-sm font-medium text-rubric outline-none transition hover:border-rubric focus-visible:ring-2 focus-visible:ring-rubric focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
