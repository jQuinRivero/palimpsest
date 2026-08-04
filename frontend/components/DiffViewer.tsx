"use client";

import { useState } from "react";
import type { ComparisonResult, ViewMode } from "@/lib/types";
import { DiffBlockRow } from "./DiffBlockRow";
import { DiffSummaryBar } from "./DiffSummaryBar";

function ViewModeToggle({
  mode,
  onChange,
}: {
  mode: ViewMode;
  onChange: (mode: ViewMode) => void;
}) {
  return (
    <div
      className="inline-flex border border-rule"
      role="group"
      aria-label="Reading mode"
    >
      {(["synoptic", "unified"] as const).map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          aria-pressed={mode === option}
          className={`px-3 py-1.5 font-ui text-sm capitalize transition-colors ${
            mode === option
              ? "bg-vellum text-ink"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function PaneHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 border-b border-rule pb-2 font-ui text-xs font-semibold uppercase tracking-widest text-ink-muted">
      {children}
    </h2>
  );
}

/**
 * The reading surface.
 *
 * Renders a finished `ComparisonResult`; it never computes a diff. Phase 1
 * implements synoptic and unified modes with ordinary scrolling. Virtualization
 * and the anchor-linked `SyncScrollContainer` are phase 4 — note that scroll
 * sync must be anchored to aligned block pairs, never pixel- or
 * percentage-linked, because the two panes hold different amounts of text.
 */
export function DiffViewer({
  comparison,
  initialMode = "synoptic",
}: {
  comparison: ComparisonResult;
  initialMode?: ViewMode;
}) {
  const [mode, setMode] = useState<ViewMode>(initialMode);
  const blocks = comparison.blocks;

  return (
    <div data-testid="diff-viewer" data-view={mode}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="font-ui text-sm text-ink-muted">
          <span className="text-ink">{comparison.a.title}</span>
          <span className="mx-2 text-ink-muted">against</span>
          <span className="text-ink">{comparison.b.title}</span>
        </div>
        <ViewModeToggle mode={mode} onChange={setMode} />
      </div>

      <DiffSummaryBar metrics={comparison.metrics} />

      {blocks.length === 0 ? (
        <p className="py-16 text-center font-ui text-sm text-ink-muted">
          This comparison has no blocks to display.
        </p>
      ) : mode === "synoptic" ? (
        <div className="mt-6 grid grid-cols-1 gap-x-10 md:grid-cols-2">
          <section aria-label="Manuscript A">
            <PaneHeading>Manuscript A</PaneHeading>
            {blocks.map((block) => (
              <DiffBlockRow key={`a-${block.id}`} block={block} side="a" />
            ))}
          </section>
          <section aria-label="Manuscript B">
            <PaneHeading>Manuscript B</PaneHeading>
            {blocks.map((block) => (
              <DiffBlockRow key={`b-${block.id}`} block={block} side="b" />
            ))}
          </section>
        </div>
      ) : (
        <section className="mt-6 max-w-prose" aria-label="Unified reading">
          {blocks.map((block) => (
            <DiffBlockRow key={`u-${block.id}`} block={block} side="unified" />
          ))}
        </section>
      )}
    </div>
  );
}
