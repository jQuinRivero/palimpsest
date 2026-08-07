"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ComparisonResult, ViewMode } from "@/lib/types";
import { teiExportUrl } from "@/lib/api";
import { ChangeNavigator } from "./ChangeNavigator";
import { DiffSummaryBar } from "./DiffSummaryBar";
import {
  VirtualizedSynopticView,
} from "./VirtualizedSynopticView";
import { VirtualizedUnifiedView } from "./VirtualizedUnifiedView";
import type { BlockListHandle } from "./blockList";
import { useBlockNavigation } from "@/lib/hooks/useBlockNavigation";
import { useWindowedBlocks } from "@/lib/hooks/useWindowedBlocks";
import { usePrintAll } from "@/lib/hooks/usePrintAll";
import { LoadingProgress } from "./LoadingProgress";
import { StructuralSummary } from "./StructuralSummary";

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

function ExportLink({ comparisonId }: { comparisonId: string }) {
  return (
    <a
      href={teiExportUrl(comparisonId)}
      // The endpoint sends Content-Disposition, so this is an ordinary link
      // rather than a fetch: it downloads without JavaScript and there is no
      // blob to hold or revoke.
      download
      className="border border-rule px-3 py-1.5 font-ui text-sm text-ink transition-colors hover:text-rubric motion-reduce:transition-none"
      data-testid="export-tei"
    >
      Export TEI
      <span className="sr-only">
        {" "}
        — downloads this collation as a TEI P5 XML file
      </span>
    </a>
  );
}

/**
 * The reading surface.
 *
 * Renders a finished `ComparisonResult`; it never computes a diff. Synoptic
 * mode is a single virtualized list of three-cell rows, so corresponding
 * blocks share a grid row and cannot drift apart — see
 * `VirtualizedSynopticView` for why that replaced anchor-linked scroll sync.
 */
export function DiffViewer({
  comparison,
  initialMode = "synoptic",
  initialBlockIndex = null,
}: {
  comparison: ComparisonResult;
  initialMode?: ViewMode;
  /** Seeded from the server so a shared ?block= link paints correctly and
   *  server and client agree on the first render. */
  initialBlockIndex?: number | null;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<ViewMode>(
    searchParams.get("view") === "unified" ? "unified" : initialMode,
  );
  const [movesEnabled, setMovesEnabled] = useState(searchParams.get("moves") !== "off");
  const windowed = useWindowedBlocks(comparison);
  const blocks = windowed.blocks;

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

  const readingRef = useRef<BlockListHandle | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const nav = useBlockNavigation(blocks, initialBlockIndex, windowed.totalBlocks);
  const printAll = usePrintAll();

  // Marks the point at which the keyboard bindings and click handlers are
  // actually attached. The viewer is server-rendered, so it is visible and
  // reads as ready well before any of it responds; a test — or a fast reader —
  // pressing `j` in that window loses the keystroke silently. Set on the DOM
  // rather than through state because nothing about the rendering depends on
  // it, and a re-render for a test seam would be a poor trade.
  useEffect(() => {
    rootRef.current?.setAttribute("data-hydrated", "true");
  }, []);

  // A virtualized row may never have been mounted, so scrolling to a block
  // must go through the virtualizer rather than through the DOM. Both reading
  // surfaces answer to the same handle, so this no longer cares which is on
  // screen — before, unified was excluded and silently relied on the DOM.
  useEffect(() => {
    if (nav.activeBlockIndex === null) return;
    readingRef.current?.scrollToBlock(nav.activeBlockIndex);
  }, [mode, nav.activeBlockIndex]);

  return (
    <div
      ref={rootRef}
      data-testid="diff-viewer"
      data-view={mode}
      data-moves={movesEnabled ? "on" : "off"}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="font-ui text-sm text-ink-muted">
          <span className="text-ink">{comparison.a.title}</span>
          <span className="mx-2 text-ink-muted">against</span>
          <span className="text-ink">{comparison.b.title}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ChangeNavigator
            activeBlockIndex={nav.activeBlockIndex}
            activeChangedPosition={nav.activeChangedPosition}
            totalChanges={nav.totalChanges}
            partial={!windowed.isComplete}
            onPrevious={nav.previous}
            onNext={nav.next}
            onClear={nav.clear}
          />
          <MovesToggle enabled={movesEnabled} onChange={changeMovesEnabled} />
          <ViewModeToggle mode={mode} onChange={changeMode} />
          <ExportLink comparisonId={comparison.comparison_id} />
        </div>
      </div>

      <DiffSummaryBar metrics={comparison.metrics} />

      <LoadingProgress
        loadedBlocks={blocks.length}
        totalBlocks={windowed.totalBlocks}
        isComplete={windowed.isComplete}
        error={windowed.error}
        onRetry={windowed.retry}
      />

      <StructuralSummary
        blocks={blocks}
        visible={movesEnabled}
        complete={windowed.isComplete}
      />

      {blocks.length === 0 ? (
        <p className="py-16 text-center font-ui text-sm text-ink-muted">
          This comparison has no blocks to display.
        </p>
      ) : mode === "synoptic" ? (
        <VirtualizedSynopticView
          ref={readingRef}
          blocks={blocks}
          showStructuralMarkers={movesEnabled}
          renderAll={printAll}
        />
      ) : (
        <VirtualizedUnifiedView
          ref={readingRef}
          blocks={blocks}
          showStructuralMarkers={movesEnabled}
          renderAll={printAll}
        />
      )}
    </div>
  );
}
