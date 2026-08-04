"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ComparisonResult, ViewMode } from "@/lib/types";
import { teiExportUrl } from "@/lib/api";
import { ChangeNavigator } from "./ChangeNavigator";
import { DiffBlockRow } from "./DiffBlockRow";
import { DiffSummaryBar } from "./DiffSummaryBar";
import {
  VirtualizedSynopticView,
  type SynopticHandle,
} from "./VirtualizedSynopticView";
import { useBlockNavigation } from "@/lib/hooks/useBlockNavigation";

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

  const synopticRef = useRef<SynopticHandle | null>(null);
  const nav = useBlockNavigation(blocks, initialBlockIndex);

  // A virtualized row may never have been mounted, so scrolling to a block
  // must go through the virtualizer rather than through the DOM.
  useEffect(() => {
    if (nav.activeBlockIndex === null) return;
    if (mode !== "synoptic") return;
    synopticRef.current?.scrollToBlock(nav.activeBlockIndex);
  }, [mode, nav.activeBlockIndex]);

  return (
    <div data-testid="diff-viewer" data-view={mode} data-moves={movesEnabled ? "on" : "off"}>
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

      {blocks.length === 0 ? (
        <p className="py-16 text-center font-ui text-sm text-ink-muted">
          This comparison has no blocks to display.
        </p>
      ) : mode === "synoptic" ? (
        <VirtualizedSynopticView
          ref={synopticRef}
          blocks={blocks}
          showStructuralMarkers={movesEnabled}
        />
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
