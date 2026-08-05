import type { DiffBlock } from "@/lib/types";
import { ChangeGutter } from "./ChangeGutter";
import { TokenStream } from "./TokenSpan";

/** Headings keep their prominence; artifact blocks recede. */
function proseClass(kind: DiffBlock["kind"]): string {
  switch (kind) {
    case "HEADING":
      return "font-manuscript text-xl font-semibold text-ink";
    case "QUOTE":
      return "font-manuscript border-l-2 border-rule pl-4 italic text-ink";
    case "VERSE_LINE":
      // Hanging indent. A verse line too long for the measure must wrap in a
      // way the reader cannot mistake for a line break, because in poetry the
      // line break is the meaning and a false one misreads the poem.
      return "font-manuscript text-ink pl-6 -indent-6";
    case "LIST_ITEM":
      return "font-manuscript text-ink";
    case "ARTIFACT":
      return "font-mono text-xs text-ink-muted";
    default:
      return "font-manuscript text-ink";
  }
}

/**
 * Vertical rhythm.
 *
 * Verse lines are lines of one poem, not consecutive paragraphs. Giving each
 * the spacing of a paragraph sets a stanza double-spaced and destroys its
 * shape on the page.
 */
function spacingClass(kind: DiffBlock["kind"]): string {
  return kind === "VERSE_LINE" ? "py-0.5" : "py-2";
}

function structuralClass(block: DiffBlock): string {
  switch (block.status) {
    case "MOVED":
    case "SPLIT":
    case "MERGED":
      return "border-l-2 border-moved bg-moved-underlay pl-2";
    default:
      return "";
  }
}

function movementPhrase(moveDistance: number | null | undefined): string {
  if (moveDistance === null || moveDistance === undefined || moveDistance === 0) {
    return "moved to a different position";
  }

  const magnitude = Math.abs(moveDistance);
  const plural = magnitude === 1 ? "block" : "blocks";
  return `moved ${magnitude} ${plural} ${moveDistance < 0 ? "earlier" : "later"}`;
}

function relationshipLabel(block: DiffBlock, side: "a" | "b" | "unified"): string | null {
  const pane =
    side === "a" ? "Manuscript A" : side === "b" ? "Manuscript B" : "unified reading";

  switch (block.status) {
    case "MOVED":
      return `${pane} block ${movementPhrase(block.move_distance)}.`;
    case "SPLIT":
      return `${pane} block is part of split group ${block.group_id ?? "without an id"}.`;
    case "MERGED":
      return `${pane} block is part of merged group ${block.group_id ?? "without an id"}.`;
    default:
      return null;
  }
}

/**
 * One block in one pane.
 *
 * A block with no tokens on this side still renders a held-open gap rather
 * than disappearing: the reading eye tracks across the two panes, and a
 * collapsing row would break that correspondence.
 */
export function DiffBlockRow({
  block,
  side,
  showStructuralMarkers = true,
}: {
  block: DiffBlock;
  side: "a" | "b" | "unified";
  showStructuralMarkers?: boolean;
}) {
  const tokens =
    side === "a" ? block.a_tokens : side === "b" ? block.b_tokens : block.tokens;
  const index = side === "b" ? block.b_index : block.a_index;
  const empty = tokens.length === 0;

  return (
    <div
      className={`flex scroll-mt-24 ${spacingClass(block.kind)} ${structuralClass(block)}`}
      data-testid={`diff-block-row-${block.id}`}
      data-status={block.status}
      data-kind={block.kind}
      data-group-id={block.group_id ?? undefined}
      id={side !== "a" ? `block-${side}-${block.id}` : undefined}
    >
      <ChangeGutter
        index={index}
        status={block.status}
        moveDistance={block.move_distance}
        showStructuralMarker={showStructuralMarkers}
      />
      <div
        className={`min-w-0 flex-1 leading-manuscript ${proseClass(block.kind)}`}
        lang={undefined}
      >
        {relationshipLabel(block, side) ? (
          <span className="sr-only">{relationshipLabel(block, side)} </span>
        ) : null}
        {empty ? (
          <span
            className="block select-none"
            aria-hidden="true"
            data-testid="held-open-gap"
          >
            &nbsp;
          </span>
        ) : (
          <TokenStream tokens={tokens} />
        )}
      </div>
    </div>
  );
}
