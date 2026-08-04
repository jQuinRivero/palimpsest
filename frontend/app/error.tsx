"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto max-w-2xl px-6 py-24">
      <h1 className="font-manuscript text-3xl text-rubric">Something went wrong</h1>
      <p className="mt-4 text-ink-muted">{error.message}</p>
      <button
        type="button"
        onClick={reset}
        className="mt-8 border border-rule px-4 py-2 text-ink hover:bg-vellum"
      >
        Try again
      </button>
    </main>
  );
}
