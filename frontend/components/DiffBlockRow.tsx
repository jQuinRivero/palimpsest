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
      return "font-manuscript text-ink";
    case "LIST_ITEM":
      return "font-manuscript text-ink";
    case "ARTIFACT":
      return "font-mono text-xs text-ink-muted";
    default:
      return "font-manuscript text-ink";
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
}: {
  block: DiffBlock;
  side: "a" | "b" | "unified";
}) {
  const tokens =
    side === "a" ? block.a_tokens : side === "b" ? block.b_tokens : block.tokens;
  const index = side === "b" ? block.b_index : block.a_index;
  const empty = tokens.length === 0;

  return (
    <div
      className="flex scroll-mt-24 py-2"
      data-testid={`diff-block-row-${block.id}`}
      data-status={block.status}
      id={side !== "a" ? `block-${block.b_index ?? block.a_index}` : undefined}
    >
      <ChangeGutter index={index} status={block.status} />
      <div
        className={`min-w-0 flex-1 leading-manuscript ${proseClass(block.kind)}`}
        lang={undefined}
      >
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
