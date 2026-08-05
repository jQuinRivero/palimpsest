import { expect, test } from "@playwright/test";
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
  await page.goto(`/c/${id}?view=unified`);

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
  await page.goto(`/c/${id}?view=unified`);

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

  await page.goto(`/c/${id}`);
  await expect(page.getByTestId("diff-viewer")).toBeVisible();
});

test("verse lines are set closer together than paragraphs", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request, STANZA, REVISED);
  await page.goto(`/c/${id}?view=unified`);

  // Wait for a row to exist before measuring it, rather than assuming the
  // render has landed. Reading computed style off a null element fails in a
  // way that looks like a styling bug and is not one.
  const row = page.locator('[data-kind="VERSE_LINE"]').first();
  await expect(row).toBeVisible();

  const paddingTop = await row.evaluate(
    (element) => parseFloat(window.getComputedStyle(element).paddingTop),
  );

  // A poem set with paragraph spacing is double-spaced and loses its shape.
  expect(paddingTop).toBeLessThan(8);
});

test("verse rendering has no accessibility violations", async ({ page, request }) => {
  const id = await comparisonFor(request, STANZA, REVISED);

  for (const view of ["synoptic", "unified"]) {
    await page.goto(`/c/${id}?view=${view}`);
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
