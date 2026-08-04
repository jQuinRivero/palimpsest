import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-24">
      <h1 className="font-manuscript text-3xl text-ink">Not found</h1>
      <p className="mt-4 text-ink-muted">
        This comparison may have expired. Comparisons are cached with a
        deadline, not stored indefinitely.
      </p>
      <Link href="/" className="mt-8 inline-block text-rubric underline">
        Start a new comparison
      </Link>
    </main>
  );
}
