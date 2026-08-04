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
  MOVED: { glyph: "\u21C5", tone: "text-moved", label: "moved" },
  SPLIT: { glyph: "\u2442", tone: "text-moved", label: "split" },
  MERGED: { glyph: "\u2443", tone: "text-moved", label: "merged" },
};

export function ChangeGutter({
  index,
  status,
}: {
  index: number | null;
  status: BlockStatus;
}) {
  const marker = MARKER[status] ?? MARKER.UNCHANGED;

  return (
    <div
      className="flex w-12 shrink-0 select-none items-baseline justify-end gap-1.5 pr-3 font-mono text-xs"
      aria-hidden={status === "UNCHANGED"}
    >
      <span className={marker.tone} title={marker.label}>
        {marker.glyph}
      </span>
      <span className="text-ink-muted tabular-nums">
        {index === null ? "" : index + 1}
      </span>
    </div>
  );
}
