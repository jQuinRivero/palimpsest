import type { BlockStatus, DiffBlock, Token } from "@/lib/types";

const STRUCTURAL_STATUSES = new Set<BlockStatus>(["MOVED", "SPLIT", "MERGED"]);
const MAX_ITEMS = 12;
const EXCERPT_LENGTH = 110;

type Side = "a" | "b";

interface SourceOrderItem {
  index: number;
  text: string;
  blocks: DiffBlock[];
  structural: boolean;
}

function tokenText(tokens: Token[]): string {
  return tokens.map((token) => token.text).join("");
}

function excerpt(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= EXCERPT_LENGTH) return normalized;
  return `${normalized.slice(0, EXCERPT_LENGTH - 1).trimEnd()}…`;
}

function sourceOrder(blocks: DiffBlock[], side: Side): SourceOrderItem[] {
  const grouped = new Map<number, { chunks: string[]; blocks: DiffBlock[] }>();

  for (const block of blocks) {
    const index = side === "a" ? block.a_index : block.b_index;
    if (index === null) continue;
    const tokens = side === "a" ? block.a_tokens : block.b_tokens;

    const current = grouped.get(index);
    if (current) {
      current.chunks.push(tokenText(tokens));
      current.blocks.push(block);
    } else {
      grouped.set(index, { chunks: [tokenText(tokens)], blocks: [block] });
    }
  }

  return [...grouped.entries()]
    .sort(([left], [right]) => left - right)
    .map(([index, group]) => ({
      index,
      text: excerpt(group.chunks.join("")),
      blocks: group.blocks,
      structural: group.blocks.some((block) => STRUCTURAL_STATUSES.has(block.status)),
    }));
}

function positions(values: Array<number | null>): string {
  return [...new Set(values.filter((value): value is number => value !== null))]
    .sort((left, right) => left - right)
    .map((value) => (value + 1).toLocaleString())
    .join(", ");
}

function relationship(item: SourceOrderItem, side: Side): string | null {
  const structural = item.blocks.find((block) => STRUCTURAL_STATUSES.has(block.status));
  if (!structural) return null;

  const otherPositions =
    side === "a"
      ? positions(item.blocks.map((block) => block.b_index))
      : positions(item.blocks.map((block) => block.a_index));
  const otherSide = side === "a" ? "B" : "A";

  switch (structural.status) {
    case "MOVED":
      return side === "a"
        ? `Moved to ${otherSide} ${otherPositions}`
        : `Moved from ${otherSide} ${otherPositions}`;
    case "SPLIT":
      return side === "a"
        ? `Split into ${otherSide} ${otherPositions}`
        : `Split from ${otherSide} ${otherPositions}`;
    case "MERGED":
      return side === "a"
        ? `Merged into ${otherSide} ${otherPositions}`
        : `Merged from ${otherSide} ${otherPositions}`;
    default:
      return null;
  }
}

function visibleItems(items: SourceOrderItem[]): {
  items: SourceOrderItem[];
  filtered: boolean;
  hidden: number;
} {
  if (items.length <= MAX_ITEMS) {
    return { items, filtered: false, hidden: 0 };
  }

  const structural = items.filter((item) => item.structural);
  return {
    items: structural.slice(0, MAX_ITEMS),
    filtered: true,
    hidden: Math.max(0, structural.length - MAX_ITEMS),
  };
}

function WitnessOrder({ items, side }: { items: SourceOrderItem[]; side: Side }) {
  const shown = visibleItems(items);
  const label = side === "a" ? "Manuscript A" : "Manuscript B";

  return (
    <div data-testid={`source-order-${side}`}>
      <h3 className="border-b border-rule pb-2 text-xs font-semibold uppercase tracking-widest text-ink-muted">
        {label}
      </h3>
      <ol className="mt-2 space-y-2">
        {shown.items.map((item) => {
          const relation = relationship(item, side);
          return (
            <li
              key={item.index}
              className={`grid grid-cols-[2rem_minmax(0,1fr)] gap-x-2 rounded-lg border px-3 py-2 ${
                item.structural
                  ? "border-moved bg-moved-underlay/30"
                  : "border-rule bg-paper"
              }`}
              data-source-index={item.index}
              data-testid={`source-order-${side}-${item.index}`}
            >
              <span className="font-mono text-xs text-ink-muted">
                {item.index + 1}
              </span>
              <span className="min-w-0 font-manuscript text-sm leading-5 text-ink">
                {item.text}
              </span>
              {relation ? (
                <span className="col-start-2 mt-1 w-fit rounded-full border border-moved px-2 py-0.5 font-ui text-[0.65rem] font-semibold uppercase tracking-wide text-moved">
                  {relation}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
      {shown.filtered ? (
        <p className="mt-2 text-xs text-ink-muted">
          Showing structurally changed passages only
          {shown.hidden > 0 ? `; ${shown.hidden} more` : ""}.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Preserve each witness's real sequence before the aligned reading rearranges
 * rows to put corresponding prose side by side.
 */
export function SourceOrderOverview({
  blocks,
  visible,
  complete,
}: {
  blocks: DiffBlock[];
  visible: boolean;
  complete: boolean;
}) {
  if (!visible || !complete) return null;
  if (!blocks.some((block) => STRUCTURAL_STATUSES.has(block.status))) return null;

  const aItems = sourceOrder(blocks, "a");
  const bItems = sourceOrder(blocks, "b");

  return (
    <section
      className="mt-4 rounded-2xl border border-rule bg-vellum/25 p-4 font-ui"
      aria-labelledby="source-order-heading"
      data-testid="source-order-overview"
    >
      <h2 id="source-order-heading" className="text-sm font-semibold text-ink">
        Original manuscript order
      </h2>
      <p className="mt-1 text-xs leading-5 text-ink-muted">
        These lists preserve the sequence in each source. The aligned reading
        below rearranges matching passages onto the same row.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2">
        <WitnessOrder items={aItems} side="a" />
        <WitnessOrder items={bItems} side="b" />
      </div>
    </section>
  );
}
