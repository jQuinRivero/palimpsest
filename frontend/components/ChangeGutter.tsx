import type { BlockStatus } from "@/lib/types";

/**
 * The marginal column carrying block ordinals and change markers — the
 * manuscript-margin analogue of a diff gutter.
 *
 * The number shown is the **block index**, not a rendered visual line number.
 * Prose reflows with viewport width, so visual lines are not stable anchors and
 * are not addressable; block ordinals are.
 */
const MARKER: Record<BlockStatus, { glyph: string; tone: string; label: string }> = {
  UNCHANGED: { glyph: "", tone: "text-ink-muted", label: "unchanged" },
  MODIFIED: { glyph: "\u2731", tone: "text-rubric", label: "modified" },
  INSERTED: { glyph: "+", tone: "text-addition", label: "inserted" },
  DELETED: { glyph: "\u2212", tone: "text-deletion", label: "deleted" },
  MOVED: { glyph: "\u25C6", tone: "text-moved", label: "moved" },
  SPLIT: { glyph: "\u2442", tone: "text-moved", label: "split" },
  MERGED: { glyph: "\u2443", tone: "text-moved", label: "merged" },
};

function movementLabel(moveDistance: number | null | undefined): string {
  if (moveDistance === null || moveDistance === undefined || moveDistance === 0) {
    return "moved block";
  }

  const magnitude = Math.abs(moveDistance);
  const direction = moveDistance < 0 ? "earlier" : "later";
  const plural = magnitude === 1 ? "block" : "blocks";
  return `moved ${magnitude} ${plural} ${direction}`;
}

export function ChangeGutter({
  index,
  status,
  moveDistance,
  showStructuralMarker = true,
}: {
  index: number | null;
  status: BlockStatus;
  moveDistance?: number | null;
  showStructuralMarker?: boolean;
}) {
  const marker = MARKER[status] ?? MARKER.UNCHANGED;
  const isStructural = status === "MOVED" || status === "SPLIT" || status === "MERGED";
  const showMarker = !isStructural || showStructuralMarker;
  const label = status === "MOVED" ? movementLabel(moveDistance) : marker.label;

  return (
    <div
      className="flex w-12 shrink-0 select-none items-baseline justify-end gap-1.5 pr-3 font-mono text-xs"
      aria-hidden={status === "UNCHANGED"}
      data-testid="change-gutter"
    >
      <span className={marker.tone} title={label} data-testid={`gutter-marker-${status}`}>
        {showMarker ? marker.glyph : ""}
      </span>
      {status !== "UNCHANGED" ? <span className="sr-only">{label}</span> : null}
      <span className="text-ink-muted tabular-nums">
        {index === null ? "" : index + 1}
      </span>
    </div>
  );
}
