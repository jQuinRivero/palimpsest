import { expect, test } from "@playwright/test";
import { gotoComparison } from "./helpers";
import AxeBuilder from "@axe-core/playwright";

/**
 * Verse, end to end.
 *
 * `BlockKind.VERSE_LINE` was unreachable until ingestion learned to segment
 * poetry: no parser ever emitted it, so the reflow exemption, the verse
 * typography and the TEI `<l>` mapping were all dead code waiting on a kind
 * that never arrived. These tests drive a real poem through the real pipeline,
 * because that is the only way to tell a reachable code path from a plausible
 * one.
 */

const API = "http://127.0.0.1:8000";

const STANZA = [
  "Shall I compare thee to a summer's day?",
  "Thou art more lovely and more temperate:",
  "Rough winds do shake the darling buds of May,",
  "And summer's lease hath all too short a date:",
].join("\n");

const REVISED = STANZA.replace("lovely", "comely");

// The second and third lines exchanged: a transposition inside a stanza.
const TRANSPOSED = [
  "Shall I compare thee to a summer's day?",
  "Rough winds do shake the darling buds of May,",
  "Thou art more lovely and more temperate:",
  "And summer's lease hath all too short a date:",
].join("\n");

async function comparisonFor(
  request: import("@playwright/test").APIRequestContext,
  aText: string,
  bText: string,
): Promise<string> {
  const upload = async (text: string, name: string) => {
    const response = await request.post(`${API}/api/v1/documents`, {
      multipart: {
        file: { name, mimeType: "text/plain", buffer: Buffer.from(text, "utf8") },
      },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    return (await response.json()).id as string;
  };

  const created = await request.post(`${API}/api/v1/comparisons`, {
    data: {
      a_document_id: await upload(aText, "verse-a.txt"),
      b_document_id: await upload(bText, "verse-b.txt"),
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  return (await created.json()).comparison_id as string;
}

test("a poem is read as lines, not as a paragraph", async ({ page, request }) => {
  const id = await comparisonFor(request, STANZA, REVISED);
  await gotoComparison(page, `/c/${id}?view=unified`);

  const verse = page.locator('[data-testid^="diff-block-row-"][data-kind="VERSE_LINE"]');
  await expect(verse).toHaveCount(4);

  // Only the revised line is marked. A stanza-sized block would have reported
  // the whole quatrain as modified for the sake of one word.
  const modified = page.locator(
    '[data-testid^="diff-block-row-"][data-kind="VERSE_LINE"][data-status="MODIFIED"]',
  );
  await expect(modified).toHaveCount(1);
  await expect(modified).toContainText("comely");
});

test("a transposed line reads as a move with no wording change", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request, STANZA, TRANSPOSED);
  await gotoComparison(page, `/c/${id}?view=unified`);

  await expect(
    page.locator('[data-kind="VERSE_LINE"][data-status="MOVED"]').first(),
  ).toBeVisible();

  // The whole point: reordering lines changes no words. Before segmentation
  // this finding did not exist at all, because moves are detected between
  // blocks and the stanza was one block.
  await expect(page.getByTestId("diff-summary-bar")).toContainText(
    /no wording changes/i,
  );
});

test("the reader is told the text was read as verse", async ({ page, request }) => {
  // Segmentation changes the unit of comparison, so it must never be silent.
  const id = await comparisonFor(request, STANZA, REVISED);
  const response = await request.get(`${API}/api/v1/comparisons/${id}`);
  const body = await response.json();

  const codes = [...body.a.warnings, ...body.b.warnings].map(
    (warning: { code: string }) => warning.code,
  );
  expect(codes).toContain("VERSE_SEGMENTED");

  await gotoComparison(page, `/c/${id}`);
  await expect(page.getByTestId("diff-viewer")).toBeVisible();
});

test("verse lines are set closer together than paragraphs", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request, STANZA, REVISED);
  await gotoComparison(page, `/c/${id}?view=unified`);

  // A line that opens a stanza deliberately takes the gap back, so measure one
  // inside the stanza instead.
  const row = page.locator('[data-kind="VERSE_LINE"][data-stanza="NONE"]').first();
  await expect(row).toBeVisible();

  const paddingTop = await row.evaluate(
    (element) => parseFloat(window.getComputedStyle(element).paddingTop),
  );

  // A poem set with paragraph spacing is double-spaced and loses its shape.
  expect(paddingTop).toBeLessThan(8);
});

test("a line opening a stanza takes the blank line back", async ({ page, request }) => {
  const id = await comparisonFor(request, STANZA, REVISED);
  await gotoComparison(page, `/c/${id}?view=unified`);

  const opening = page.locator('[data-kind="VERSE_LINE"][data-stanza="SHARED"]').first();
  await expect(opening).toBeVisible();

  const paddingTop = await opening.evaluate(
    (element) => parseFloat(window.getComputedStyle(element).paddingTop),
  );

  // The blank line between stanzas is part of the poem's form, not slack.
  expect(paddingTop).toBeGreaterThan(8);
});

test("verse rendering has no accessibility violations", async ({ page, request }) => {
  const id = await comparisonFor(request, STANZA, REVISED);

  for (const view of ["synoptic", "unified"]) {
    await gotoComparison(page, `/c/${id}?view=${view}`);
    await expect(page.getByTestId("diff-viewer")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    expect(
      results.violations,
      `${view}: ${results.violations.map((v) => `${v.id} (${v.nodes.length})`).join(", ")}`,
    ).toEqual([]);
  }
});

const OCTAVE = [
  "Shall I compare thee to a summer's day?",
  "Thou art more lovely and more temperate:",
  "Rough winds do shake the darling buds of May,",
  "And summer's lease hath all too short a date:",
  "Sometime too hot the eye of heaven shines,",
  "And often is his gold complexion dimm'd;",
];

const AS_ONE_STANZA = OCTAVE.join("\n");
const AS_TWO_STANZAS = OCTAVE.slice(0, 3).join("\n") + "\n\n" + OCTAVE.slice(3).join("\n");

test("dividing a poem into two stanzas is reported, though no word changes", async ({
  page,
  request,
}) => {
  // Without this the collation reported similarity 1.000 and no finding at
  // all: the tool asserting that two formally different poems were the same.
  const id = await comparisonFor(request, AS_ONE_STANZA, AS_TWO_STANZAS);
  await gotoComparison(page, `/c/${id}?view=unified`);

  const summary = page.getByTestId("diff-summary-bar");
  await expect(summary).toContainText(/no wording changes/i);
  await expect(summary).toContainText("1 stanza break changed");

  // And the line where the break appears is marked, so the reader can see
  // where it is rather than only that it exists.
  await expect(page.locator('[data-stanza="B_ONLY"]')).toHaveCount(1);
});

test("a poem with matching stanzas reports no stanza change", async ({ page, request }) => {
  const id = await comparisonFor(request, AS_TWO_STANZAS, AS_TWO_STANZAS);
  await gotoComparison(page, `/c/${id}?view=unified`);

  await expect(page.getByTestId("diff-summary-bar")).not.toContainText("stanza break");
  await expect(page.locator('[data-stanza="A_ONLY"]')).toHaveCount(0);
  await expect(page.locator('[data-stanza="B_ONLY"]')).toHaveCount(0);

  // Stanza openings are still marked, which is what draws the gap.
  await expect(page.locator('[data-stanza="SHARED"]')).toHaveCount(2);
});
