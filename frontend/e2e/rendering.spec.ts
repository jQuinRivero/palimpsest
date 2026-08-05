import { expect, test } from "@playwright/test";
import { gotoComparison } from "./helpers";

/**
 * What is actually in the DOM.
 *
 * Two failures live here, and they pull against each other. On screen the
 * reading surfaces must mount a bounded window regardless of manuscript
 * length, or a long comparison stops responding. On paper they must mount
 * everything, or the reader carries away a fragment with nothing on it to say
 * so — the same failure as rendering a truncated comparison as a whole one,
 * except the artifact leaves the building.
 *
 * Both were real. Unified rendered one row per block, unbounded, which the
 * windowed loader then made worse by supplying every block. Printing from
 * synoptic produced 42 of 300 blocks.
 */

const API = "http://127.0.0.1:8000";
const BLOCK_COUNT = 300;

/** Doc 11's budget, with room for overscan on a tall viewport. */
const MOUNTED_ROW_BUDGET = 120;

function witness(revised: boolean): string {
  const paragraphs: string[] = [];
  for (let index = 0; index < BLOCK_COUNT; index += 1) {
    paragraphs.push(
      revised && index % 10 === 0
        ? `Paragraph ${index} of the witness, revised here with different wording entirely.`
        : `Paragraph ${index} of the witness, carrying enough words to be a real block.`,
    );
  }
  return paragraphs.join("\n\n");
}

let comparisonId: string;
let totalBlocks: number;

test.beforeAll(async ({ request }) => {
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
      a_document_id: await upload(witness(false), "render-a.txt"),
      b_document_id: await upload(witness(true), "render-b.txt"),
    },
  });
  expect(created.status(), await created.text()).toBe(201);

  const body = await created.json();
  comparisonId = body.comparison_id as string;
  totalBlocks = body.total_blocks as number;
  expect(totalBlocks).toBeGreaterThan(MOUNTED_ROW_BUDGET);
});

async function openLoaded(page: import("@playwright/test").Page, view: string) {
  await gotoComparison(page, `/c/${comparisonId}?view=${view}`);
  await expect(page.getByTestId("block-loading-status")).toHaveAttribute(
    "data-state",
    "complete",
    { timeout: 30_000 },
  );
}

function rowCount(page: import("@playwright/test").Page) {
  return page.evaluate(
    () => document.querySelectorAll('[data-testid^="diff-block-row-"]').length,
  );
}

for (const view of ["synoptic", "unified"] as const) {
  test(`${view} mounts a bounded window on screen`, async ({ page }) => {
    await openLoaded(page, view);

    const mounted = await rowCount(page);
    // Synoptic renders each block twice, once per witness, so the budget is
    // compared against rows rather than against blocks.
    expect(mounted).toBeLessThanOrEqual(MOUNTED_ROW_BUDGET);
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThan(totalBlocks);
  });

  test(`${view} prints the whole comparison`, async ({ page }) => {
    await openLoaded(page, view);
    expect(await rowCount(page)).toBeLessThanOrEqual(MOUNTED_ROW_BUDGET);

    await page.emulateMedia({ media: "print" });

    // Every block, in whichever multiple the view renders them.
    await expect
      .poll(() => rowCount(page), { timeout: 15_000 })
      .toBeGreaterThanOrEqual(totalBlocks);

    await page.emulateMedia({ media: "screen" });

    // And the window returns afterwards, rather than leaving the tab holding
    // the entire manuscript for the rest of the session.
    await expect.poll(() => rowCount(page), { timeout: 15_000 }).toBeLessThanOrEqual(
      MOUNTED_ROW_BUDGET,
    );
  });
}

test("unified navigation reaches a block outside the mounted window", async ({ page }) => {
  // Unified was not virtualized, so navigation there relied on the block
  // already being in the DOM. It now goes through the virtualizer like
  // synoptic, and this is what proves it.
  const target = totalBlocks - 3;
  await gotoComparison(page, `/c/${comparisonId}?view=unified&block=${target}`);
  await expect(page.getByTestId("block-loading-status")).toHaveAttribute(
    "data-state",
    "complete",
    { timeout: 30_000 },
  );

  await expect(page.getByTestId("diff-viewer")).toHaveAttribute("data-view", "unified");
  await expect(page).toHaveURL(new RegExp(`block=${target}`));

  // The virtualizer must have scrolled far enough that the requested block is
  // among the mounted rows.
  await expect
    .poll(
      () =>
        page.evaluate((index) => {
          const rows = document.querySelectorAll("[data-block-index]");
          const indices = Array.from(rows, (row) =>
            Number(row.getAttribute("data-block-index")),
          );
          return indices.length === 0 ? -1 : Math.max(...indices) >= index ? 1 : 0;
        }, target),
      { timeout: 15_000 },
    )
    .not.toBe(0);
});
