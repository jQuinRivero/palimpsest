import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * Structural change, end to end against the real backend.
 *
 * These tests drive the actual API, which emits MOVED, SPLIT and MERGED, and
 * assert what a researcher would really see in the real components.
 *
 * A sibling `structural.spec.ts` once covered this ground by serving a
 * hand-written HTML page through `page.route`. It was deleted: because the
 * comparison route fetches in a server component, `page.route` never sees the
 * request, so the fixture had to reimplement the gutter glyphs, connectors and
 * moves toggle inside the test file and then assert against its own output.
 * That is a tautology — it would have passed with the real components broken
 * or absent. Anything worth asserting is asserted here instead.
 */

const API = "http://127.0.0.1:8000";

async function comparisonFor(
  request: import("@playwright/test").APIRequestContext,
  aText: string,
  bText: string,
): Promise<string> {
  const directory = mkdtempSync(join(tmpdir(), "palimpsest-structural-"));

  const upload = async (text: string, name: string) => {
    const path = join(directory, name);
    writeFileSync(path, text, "utf8");
    const response = await request.post(`${API}/api/v1/documents`, {
      multipart: {
        file: { name, mimeType: "text/plain", buffer: Buffer.from(text, "utf8") },
      },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    return (await response.json()).id as string;
  };

  const aId = await upload(aText, "a.txt");
  const bId = await upload(bText, "b.txt");

  const created = await request.post(`${API}/api/v1/comparisons`, {
    data: { a_document_id: aId, b_document_id: bId },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  return (await created.json()).comparison_id as string;
}

const MOVE_A =
  "Alpha paragraph stands here at the beginning.\n\n" +
  "Beta paragraph follows it closely.\n\n" +
  "Gamma paragraph ends the sequence.";
const MOVE_B =
  "Gamma paragraph ends the sequence.\n\n" +
  "Alpha paragraph stands here at the beginning.\n\n" +
  "Beta paragraph follows it closely.";

const SPLIT_A =
  "It was a long crossing. The waves were grey from the first morning to the last.";
const SPLIT_B =
  "It was a long crossing.\n\nThe waves were grey from the first morning to the last.";

// A merge is a split read backwards, so the same prose exercises both.
const MERGE_A = SPLIT_B;
const MERGE_B = SPLIT_A;

// The glyphs the gutter actually renders. Asserting them here rather than
// recomputing them keeps the reader-facing vocabulary under test.
const GLYPH = { MOVED: "\u25C6", SPLIT: "\u2442", MERGED: "\u2443" } as const;

test("a moved passage reads as moved, not as a deletion and an insertion", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request, MOVE_A, MOVE_B);
  await page.goto(`/c/${id}`);

  await expect(page.getByTestId("diff-viewer")).toBeVisible();

  const moved = page.locator('[data-status="MOVED"]');
  await expect(moved.first()).toBeVisible();

  const marker = page.getByTestId("gutter-marker-MOVED").first();
  await expect(marker).toBeVisible();
  await expect(marker).toHaveText(GLYPH.MOVED);

  // The distance is the whole information content of a move marker: "moved"
  // alone does not tell a reader where the passage went.
  await expect(marker).toHaveAttribute("title", /^moved \d+ blocks? (earlier|later)$/);

  // The whole point: a move changes no words, so the summary must not claim
  // any were inserted or deleted.
  const summary = page.getByTestId("diff-summary-bar");
  await expect(summary).toContainText(/no wording changes/i);
});

test("a paragraph split reads as a split group with no wording change", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request, SPLIT_A, SPLIT_B);
  await page.goto(`/c/${id}`);

  const rows = page.locator('[data-testid^="diff-block-row-"][data-status="SPLIT"]');
  await expect(rows.first()).toBeVisible();

  // Two members, each rendered once per pane in synoptic view.
  await expect(rows).toHaveCount(4);

  // The members must be tied together, or the reader cannot see that the two
  // paragraphs came from one.
  await expect(page.locator('[data-testid^="block-connector-"]').first()).toBeVisible();
  await expect(page.getByTestId("gutter-marker-SPLIT").first()).toHaveText(GLYPH.SPLIT);

  // The author changed the paragraphing and not one word.
  await expect(page.getByTestId("diff-summary-bar")).toContainText(
    /no wording changes/i,
  );
});

test("a merged pair reads as a merge group with no wording change", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request, MERGE_A, MERGE_B);
  await page.goto(`/c/${id}`);

  const rows = page.locator('[data-testid^="diff-block-row-"][data-status="MERGED"]');
  await expect(rows.first()).toBeVisible();
  await expect(rows).toHaveCount(4);

  await expect(page.getByTestId("gutter-marker-MERGED").first()).toHaveText(GLYPH.MERGED);
  await expect(page.locator('[data-testid^="block-connector-"]').first()).toBeVisible();

  await expect(page.getByTestId("diff-summary-bar")).toContainText(
    /no wording changes/i,
  );
});

test("the moves toggle suppresses move affordances and survives sharing", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request, MOVE_A, MOVE_B);

  await page.goto(`/c/${id}`);
  await expect(page.getByTestId("diff-viewer")).toHaveAttribute("data-moves", "on");
  const connector = page.locator('[data-testid^="block-connector-"]').first();
  await expect(connector).toHaveAttribute("data-visible", "true");

  await page.getByTestId("moves-toggle").click();
  await expect(page.getByTestId("diff-viewer")).toHaveAttribute("data-moves", "off");
  await expect(page).toHaveURL(/moves=off/);

  // Suppressing moves must suppress every affordance, not just the toggle
  // state: a reader who turned markers off should see plain prose.
  await expect(connector).toHaveAttribute("data-visible", "false");
  await expect(page.getByTestId("gutter-marker-MOVED").first()).toHaveText("");

  // A researcher must be able to send a colleague the suppressed view.
  await page.goto(`/c/${id}?moves=off`);
  await expect(page.getByTestId("diff-viewer")).toHaveAttribute("data-moves", "off");
  await expect(
    page.locator('[data-testid^="block-connector-"]').first(),
  ).toHaveAttribute("data-visible", "false");
});

test("structural rendering has no accessibility violations", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request, MOVE_A, MOVE_B);

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
