"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import type { DiffBlock } from "@/lib/types";
import { BlockConnector } from "./BlockConnector";
import { DiffBlockRow } from "./DiffBlockRow";
import { OVERSCAN_PX, type BlockListHandle } from "./blockList";

/**
 * The synoptic reading surface, virtualized.
 *
 * Without virtualization a 100,000-word manuscript renders on the order of
 * 120,000 token spans per pane and the tab stops responding.
 * `react-virtuoso` is used because prose blocks have no knowable height in
 * advance and it measures variable-height rows automatically through
 * ResizeObserver, and because its imperative handle is what lets deep links
 * and change navigation jump to a block that has never been mounted.
 *
 * ## Why there is no anchor-linked scroll synchronisation
 *
 * The specification anticipated two independently scrolling panes tied
 * together by matching aligned block pairs, because copying one pane's scroll
 * offset or percentage to the other drifts immediately — the panes hold
 * different amounts of text.
 *
 * A single virtualized list of three-cell rows removes the problem rather than
 * solving it. Manuscript A, the connector and Manuscript B share one grid row,
 * so corresponding blocks are adjacent *by construction* and cannot drift by
 * any amount, at any scroll position, under any difference in rendered height.
 * There is one scroll position because there is one scroller.
 *
 * The cost is real and worth stating: the panes cannot be scrolled
 * independently, so a researcher cannot hold chapter two beside chapter nine.
 * That is a distinct feature rather than a degraded version of this one, and
 * it would need a deliberate second view — see docs/14-roadmap.md.
 */

export const VirtualizedSynopticView = forwardRef<
  BlockListHandle,
  {
    blocks: DiffBlock[];
    showStructuralMarkers: boolean;
    height?: string;
    /** Render every row instead of a window. Used for printing, where a
     *  virtualized list would put a fraction of the collation on paper. */
    renderAll?: boolean;
  }
>(function VirtualizedSynopticView(
  { blocks, showStructuralMarkers, height = "70vh", renderAll = false },
  ref,
) {
  const virtuoso = useRef<VirtuosoHandle | null>(null);

  useImperativeHandle(ref, () => ({
    scrollToBlock(index: number) {
      virtuoso.current?.scrollToIndex({ index, align: "center", behavior: "auto" });
    },
  }));

  const row = (index: number, block: DiffBlock) => (
    <div
      className="grid grid-cols-1 gap-x-4 md:grid-cols-[minmax(0,1fr)_2rem_minmax(0,1fr)]"
      data-block-index={index}
    >
      <DiffBlockRow block={block} side="a" showStructuralMarkers={showStructuralMarkers} />
      <BlockConnector block={block} showMoves={showStructuralMarkers} />
      <DiffBlockRow block={block} side="b" showStructuralMarkers={showStructuralMarkers} />
    </div>
  );

  return (
    <div data-testid="synoptic-view" className="mt-6">
      {/* The pane headings are the reader's primary orientation and must be
          exposed to assistive technology, not treated as decorative column
          labels. They sit outside the scroller so they stay visible while the
          virtualized rows move beneath them. */}
      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-[minmax(0,1fr)_2rem_minmax(0,1fr)]">
        <PaneHeading>Manuscript A</PaneHeading>
        <div aria-hidden="true" className="hidden md:block" />
        <PaneHeading>Manuscript B</PaneHeading>
      </div>

      {renderAll ? (
        <div data-testid="synoptic-scroller">
          {blocks.map((block, index) => (
            <div key={block.id}>{row(index, block)}</div>
          ))}
        </div>
      ) : (
        <Virtuoso
          ref={virtuoso}
          data={blocks}
          style={{ height }}
          increaseViewportBy={OVERSCAN_PX}
          data-testid="synoptic-scroller"
          // Keyed by block id rather than by index. Virtuoso defaults to the
          // index, which is fine while `blocks` is the whole comparison but
          // silently recycles a mounted row into a different block once the
          // windowed endpoint starts replacing ranges — the reader would see
          // one witness's prose under another's gutter.
          computeItemKey={(_, block) => block.id}
          itemContent={row}
        />
      )}
    </div>
  );
});

function PaneHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 border-b border-rule pb-2 font-ui text-xs font-semibold uppercase tracking-widest text-ink-muted">
      {children}
    </h2>
  );
}
