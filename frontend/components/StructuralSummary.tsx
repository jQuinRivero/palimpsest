import type { BlockStatus, DiffBlock } from "@/lib/types";

const STRUCTURAL_STATUSES = new Set<BlockStatus>(["MOVED", "SPLIT", "MERGED"]);
const MAX_VISIBLE_RELATIONSHIPS = 5;

interface StructuralRelationship {
  key: string;
  status: "MOVED" | "SPLIT" | "MERGED";
  description: string;
}

function uniqueIndices(values: Array<number | null>): number[] {
  return [...new Set(values.filter((value): value is number => value !== null))].sort(
    (left, right) => left - right,
  );
}

function joinPositions(indices: number[]): string {
  const positions = indices.map((index) => (index + 1).toLocaleString());
  if (positions.length === 1) return positions[0];
  if (positions.length === 2) return `${positions[0]} and ${positions[1]}`;
  return `${positions.slice(0, -1).join(", ")}, and ${positions.at(-1)}`;
}

function passage(indices: number[]): string {
  return `${indices.length === 1 ? "passage" : "passages"} ${joinPositions(indices)}`;
}

/**
 * Turn the payload's structural groups into sentences rather than asking a
 * reader to decode a diamond, arrow, fork, and two block ordinals.
 */
export function structuralRelationships(blocks: DiffBlock[]): StructuralRelationship[] {
  const groups = new Map<string, DiffBlock[]>();

  for (const block of blocks) {
    if (!STRUCTURAL_STATUSES.has(block.status)) continue;

    const key =
      block.status === "MOVED"
        ? `MOVED:${block.id}`
        : `${block.status}:${block.group_id ?? block.id}`;
    const group = groups.get(key);
    if (group) {
      group.push(block);
    } else {
      groups.set(key, [block]);
    }
  }

  const relationships: StructuralRelationship[] = [];
  for (const [key, group] of groups) {
    const status = group[0].status;
    const aIndices = uniqueIndices(group.map((block) => block.a_index));
    const bIndices = uniqueIndices(group.map((block) => block.b_index));
    if (aIndices.length === 0 || bIndices.length === 0) continue;

    if (status === "MOVED") {
      relationships.push({
        key,
        status,
        description: `${passage(aIndices)} in Manuscript A appears as ${passage(bIndices)} in Manuscript B.`,
      });
    } else if (status === "SPLIT") {
      relationships.push({
        key,
        status,
        description: `${passage(aIndices)} in Manuscript A became ${passage(bIndices)} in Manuscript B.`,
      });
    } else if (status === "MERGED") {
      relationships.push({
        key,
        status,
        description: `${passage(aIndices)} in Manuscript A became ${passage(bIndices)} in Manuscript B.`,
      });
    }
  }

  return relationships;
}

function displayStatus(status: StructuralRelationship["status"]): string {
  switch (status) {
    case "MOVED":
      return "Moved";
    case "SPLIT":
      return "Split";
    case "MERGED":
      return "Merged";
  }
}

/**
 * A prose explanation of the structural marks in the reading surface.
 *
 * Details are withheld until every block has loaded: a split group whose
 * second member is still outside the window would otherwise be described as a
 * one-to-one relationship, which is exactly the kind of plausible lie this
 * component exists to prevent.
 */
export function StructuralSummary({
  blocks,
  visible,
  complete,
}: {
  blocks: DiffBlock[];
  visible: boolean;
  complete: boolean;
}) {
  if (!visible || !complete) return null;

  const relationships = structuralRelationships(blocks);
  if (relationships.length === 0) return null;

  const visibleRelationships = relationships.slice(0, MAX_VISIBLE_RELATIONSHIPS);
  const hiddenCount = relationships.length - visibleRelationships.length;

  return (
    <section
      className="mt-4 rounded-2xl border border-moved bg-moved-underlay/30 p-4 font-ui text-sm text-ink"
      aria-labelledby="structural-summary-heading"
      data-testid="structural-summary"
    >
      <h2 id="structural-summary-heading" className="font-semibold">
        What changed structurally
      </h2>
      <ul className="mt-2 space-y-2">
        {visibleRelationships.map((relationship) => (
          <li
            key={relationship.key}
            className="flex items-start gap-3"
            data-testid={`structural-relationship-${relationship.status}`}
          >
            <span className="mt-0.5 min-w-16 rounded-full border border-moved px-2 py-0.5 text-center text-xs font-semibold text-moved">
              {displayStatus(relationship.status)}
            </span>
            <span>{relationship.description}</span>
          </li>
        ))}
      </ul>
      {hiddenCount > 0 ? (
        <p className="mt-3 text-xs text-ink-muted">
          {hiddenCount.toLocaleString()} more structural{" "}
          {hiddenCount === 1 ? "change" : "changes"} — use Next to visit each one.
        </p>
      ) : null}
    </section>
  );
}
