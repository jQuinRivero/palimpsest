"use client";

import type { BlockStatus, DiffBlock } from "@/lib/types";

const STRUCTURAL_STATUSES = new Set<BlockStatus>(["MOVED", "SPLIT", "MERGED"]);

function connectorGlyph(block: DiffBlock): string {
  switch (block.status) {
    case "SPLIT":
      return "┬";
    case "MERGED":
      return "┴";
    case "MOVED":
      if ((block.move_distance ?? 0) < 0) {
        return "↑";
      }
      if ((block.move_distance ?? 0) > 0) {
        return "↓";
      }
      return "◆";
    default:
      return "";
  }
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
      <div className="relative flex min-h-12 w-7 items-center justify-center text-moved transition-opacity motion-reduce:transition-none">
        <span className="absolute inset-y-2 left-1/2 border-l border-moved" />
        <span className="relative bg-paper px-1 font-mono text-sm leading-none">
          {connectorGlyph(block)}
        </span>
      </div>
    </div>
  );
}
