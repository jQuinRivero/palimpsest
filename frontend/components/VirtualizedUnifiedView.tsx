"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import type { DiffBlock } from "@/lib/types";
import { DiffBlockRow } from "./DiffBlockRow";
import { OVERSCAN_PX, type BlockListHandle } from "./blockList";

/**
 * The unified reading surface, virtualized.
 *
 * Unified used to render one row per block with no windowing. That was
 * survivable while the client only ever held the server's first window, and
 * stopped being survivable the moment it started loading the whole
 * comparison: rows scale one-to-one with blocks, so a long manuscript mounted
 * thousands of them against a documented budget of about a hundred.
 *
 * Both reading surfaces are now the same shape — a `react-virtuoso` list of
 * `DiffBlock` rows behind a `BlockListHandle` — which is also what lets
 * navigation scroll to a block without knowing which view is on screen.
 */
export const VirtualizedUnifiedView = forwardRef<
  BlockListHandle,
  {
    blocks: DiffBlock[];
    showStructuralMarkers: boolean;
    height?: string;
    /** Render every row instead of a window. Used for printing, where a
     *  virtualized list would put a fraction of the collation on paper. */
    renderAll?: boolean;
  }
>(function VirtualizedUnifiedView(
  { blocks, showStructuralMarkers, height = "70vh", renderAll = false },
  ref,
) {
  const virtuoso = useRef<VirtuosoHandle | null>(null);

  useImperativeHandle(ref, () => ({
    scrollToBlock(index: number) {
      virtuoso.current?.scrollToIndex({ index, align: "center", behavior: "auto" });
    },
  }));

  const row = (block: DiffBlock) => (
    <DiffBlockRow
      block={block}
      side="unified"
      showStructuralMarkers={showStructuralMarkers}
    />
  );

  return (
    <section className="mt-6 max-w-prose" aria-label="Unified reading" data-testid="unified-view">
      {renderAll ? (
        blocks.map((block) => <div key={block.id}>{row(block)}</div>)
      ) : (
        <Virtuoso
          ref={virtuoso}
          data={blocks}
          style={{ height }}
          increaseViewportBy={OVERSCAN_PX}
          computeItemKey={(_, block) => block.id}
          itemContent={(_, block) => row(block)}
        />
      )}
    </section>
  );
});
