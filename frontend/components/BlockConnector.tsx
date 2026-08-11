"use client";

import type { BlockStatus, DiffBlock } from "@/lib/types";

const STRUCTURAL_STATUSES = new Set<BlockStatus>(["MOVED", "SPLIT", "MERGED"]);

function statusLabel(block: DiffBlock): string {
  switch (block.status) {
    case "SPLIT":
      return "Split";
    case "MERGED":
      return "Merged";
    case "MOVED":
      if ((block.move_distance ?? 0) < 0) {
        return "Moved up";
      }
      if ((block.move_distance ?? 0) > 0) {
        return "Moved down";
      }
      return "Moved";
    default:
      return "";
  }
}

function position(index: number | null): string {
  return index === null ? "—" : (index + 1).toLocaleString();
}

/**
 * Decorative manuscript-margin tie for structural block relationships.
 *
 * The text alternative lives on `DiffBlockRow`; this connector is deliberately
 * hidden from assistive technology so the relationship is not announced twice.
 */
export function BlockConnector({
  block,
  showMoves = true,
}: {
  block: DiffBlock;
  aRect?: DOMRectReadOnly;
  bRect?: DOMRectReadOnly;
  showMoves?: boolean;
}) {
  if (!showMoves || !STRUCTURAL_STATUSES.has(block.status)) {
    return (
      <div
        className="hidden md:block"
        data-testid={`block-connector-${block.id}`}
        data-visible="false"
      />
    );
  }

  return (
    <div
      aria-hidden="true"
      className="hidden select-none items-stretch justify-center md:flex"
      data-testid={`block-connector-${block.id}`}
      data-status={block.status}
      data-visible="true"
      data-group-id={block.group_id ?? undefined}
    >
      <div className="relative flex min-h-12 w-full flex-col items-center justify-center gap-1 text-moved transition-opacity motion-reduce:transition-none">
        <span className="absolute inset-y-1 left-1/2 border-l border-moved" />
        <span
          className="relative whitespace-nowrap rounded-full border border-moved bg-paper px-2 py-0.5 font-ui text-[0.65rem] font-semibold uppercase tracking-wide"
          data-testid={`connector-status-${block.status}`}
        >
          {statusLabel(block)}
        </span>
        <span
          className="relative whitespace-nowrap rounded border border-moved bg-paper px-1.5 py-0.5 font-mono text-xs font-semibold"
          data-testid={`connector-positions-${block.status}`}
        >
          A {position(block.a_index)} → B {position(block.b_index)}
        </span>
      </div>
    </div>
  );
}
