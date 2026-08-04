"use client";

import { Fragment, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ComparisonResult, ViewMode } from "@/lib/types";
import { BlockConnector } from "./BlockConnector";
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

function MovesToggle({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      aria-pressed={enabled}
      className="border border-rule px-3 py-1.5 font-ui text-sm text-ink transition-colors hover:text-rubric motion-reduce:transition-none"
      data-testid="moves-toggle"
    >
      Structural markers {enabled ? "on" : "off"}
    </button>
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
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<ViewMode>(
    searchParams.get("view") === "unified" ? "unified" : initialMode,
  );
  const [movesEnabled, setMovesEnabled] = useState(searchParams.get("moves") !== "off");
  const blocks = comparison.blocks;

  const replaceUrlState = useMemo(
    () => (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null) {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      }

      const query = params.toString();
      const nextUrl = query ? `${pathname}?${query}` : pathname;

      if (typeof window === "undefined") {
        router.replace(nextUrl, { scroll: false });
        return;
      }

      window.history.replaceState(null, "", nextUrl);
    },
    [pathname, router, searchParams],
  );

  const changeMode = (nextMode: ViewMode) => {
    setMode(nextMode);
    replaceUrlState({ view: nextMode === "synoptic" ? null : nextMode });
  };

  const changeMovesEnabled = (enabled: boolean) => {
    setMovesEnabled(enabled);
    replaceUrlState({ moves: enabled ? null : "off" });
  };

  return (
    <div data-testid="diff-viewer" data-view={mode} data-moves={movesEnabled ? "on" : "off"}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="font-ui text-sm text-ink-muted">
          <span className="text-ink">{comparison.a.title}</span>
          <span className="mx-2 text-ink-muted">against</span>
          <span className="text-ink">{comparison.b.title}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <MovesToggle enabled={movesEnabled} onChange={changeMovesEnabled} />
          <ViewModeToggle mode={mode} onChange={changeMode} />
        </div>
      </div>

      <DiffSummaryBar metrics={comparison.metrics} />

      {blocks.length === 0 ? (
        <p className="py-16 text-center font-ui text-sm text-ink-muted">
          This comparison has no blocks to display.
        </p>
      ) : mode === "synoptic" ? (
        <div className="mt-6 grid grid-cols-1 gap-y-3 md:grid-cols-[minmax(0,1fr)_2rem_minmax(0,1fr)] md:gap-x-4">
          <section aria-label="Manuscript A" className="md:col-start-1">
            <PaneHeading>Manuscript A</PaneHeading>
          </section>
          <div aria-hidden="true" className="hidden md:block" />
          <section aria-label="Manuscript B" className="md:col-start-3">
            <PaneHeading>Manuscript B</PaneHeading>
          </section>
          {blocks.map((block) => (
            <Fragment key={`synoptic-${block.id}`}>
              <DiffBlockRow
                block={block}
                side="a"
                showStructuralMarkers={movesEnabled}
              />
              <BlockConnector block={block} showMoves={movesEnabled} />
              <DiffBlockRow
                block={block}
                side="b"
                showStructuralMarkers={movesEnabled}
              />
            </Fragment>
          ))}
        </div>
      ) : (
        <section className="mt-6 max-w-prose" aria-label="Unified reading">
          {blocks.map((block) => (
            <DiffBlockRow
              key={`u-${block.id}`}
              block={block}
              side="unified"
              showStructuralMarkers={movesEnabled}
            />
          ))}
        </section>
      )}
    </div>
  );
}
