import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * Structural change, end to end against the real backend.
 *
 * The sibling `structural.spec.ts` renders the components against a fixture,
 * which cannot exercise the real page: the comparison route fetches in a
 * server component, so `page.route` never sees the request. These tests
 * instead drive the actual API, which now emits MOVED, SPLIT and MERGED, and
 * assert what a researcher would really see.
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

test("a moved passage reads as moved, not as a deletion and an insertion", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request, MOVE_A, MOVE_B);
  await page.goto(`/c/${id}`);

  await expect(page.getByTestId("diff-viewer")).toBeVisible();

  const moved = page.locator('[data-status="MOVED"]');
  await expect(moved.first()).toBeVisible();
  await expect(page.getByTestId("gutter-marker-MOVED").first()).toBeVisible();

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
  await expect(page.getByTestId("gutter-marker-SPLIT").first()).toBeVisible();

  // The author changed the paragraphing and not one word.
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

  await page.getByTestId("moves-toggle").click();
  await expect(page.getByTestId("diff-viewer")).toHaveAttribute("data-moves", "off");
  await expect(page).toHaveURL(/moves=off/);

  // A researcher must be able to send a colleague the suppressed view.
  await page.goto(`/c/${id}?moves=off`);
  await expect(page.getByTestId("diff-viewer")).toHaveAttribute("data-moves", "off");
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
