import { expect, test } from "@playwright/test";
import { gotoComparison } from "./helpers";

/**
 * Windowed comparisons.
 *
 * A comparison above the server's window threshold arrives truncated: the
 * first window of blocks plus a total. Before this was handled, the viewer
 * rendered that window as though it were the whole collation — no indication,
 * no way to reach the rest, and a summary bar reporting metrics for blocks
 * that were not on the page. These tests exist to keep that from coming back,
 * so they assert on what the reader can reach rather than on request counts.
 *
 * The threshold is lowered for end-to-end runs (see playwright.config.ts), so
 * a few hundred blocks is enough to exercise the path that production reaches
 * at a few thousand.
 */

const API = "http://127.0.0.1:8000";

const BLOCK_COUNT = 300;
/** One change every tenth block, so changes exist well past the first window. */
const CHANGE_EVERY = 10;

function witness(revised: boolean): string {
  const paragraphs: string[] = [];
  for (let index = 0; index < BLOCK_COUNT; index += 1) {
    const changed = revised && index % CHANGE_EVERY === 0;
    paragraphs.push(
      changed
        ? `Paragraph ${index} of the witness, revised here with different wording entirely.`
        : `Paragraph ${index} of the witness, carrying enough words to be a real block.`,
    );
  }
  return paragraphs.join("\n\n");
}

let comparisonId: string;
let totalBlocks: number;
let firstWindow: number;

/**
 * Slows the window fetches so the loading state is observable.
 *
 * Without this the assertions race the network: a three-hundred-block fixture
 * can finish loading before the first expectation runs, and the test then
 * fails against the completed state for reasons that have nothing to do with
 * the behaviour under test. Delaying the continuation is deterministic, where
 * asserting quickly enough is a bet on the machine.
 */
async function withSlowWindowLoading(page: import("@playwright/test").Page) {
  await page.route("**/comparisons/*/blocks*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.continue();
  });
}

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
      a_document_id: await upload(witness(false), "windowed-a.txt"),
      b_document_id: await upload(witness(true), "windowed-b.txt"),
    },
  });
  expect(created.status(), await created.text()).toBe(201);

  const body = await created.json();
  comparisonId = body.comparison_id as string;

  // The premise of every test below: the server really did window this. If the
  // threshold is ever raised past the fixture, these tests would otherwise
  // keep passing while testing nothing.
  expect(
    body.truncated,
    "fixture must be large enough to be windowed; see playwright.config.ts",
  ).toBe(true);
  expect(body.blocks.length).toBeLessThan(body.total_blocks);

  totalBlocks = body.total_blocks as number;
  firstWindow = body.blocks.length as number;
});

test("a truncated comparison says so, then loads the whole collation", async ({ page }) => {
  await withSlowWindowLoading(page);
  await gotoComparison(page, `/c/${comparisonId}`);

  const status = page.getByTestId("block-loading-status");

  // The reader must never be shown a window that looks like the whole text.
  await expect(status).toHaveAttribute("data-state", "loading");
  await expect(status).toContainText(`of ${totalBlocks.toLocaleString()} blocks`);

  await expect(status).toHaveAttribute("data-state", "complete");
  await expect(status).toContainText(`All ${totalBlocks.toLocaleString()} blocks loaded.`);
});

test("the change count is marked provisional until everything has arrived", async ({
  page,
}) => {
  await withSlowWindowLoading(page);
  await gotoComparison(page, `/c/${comparisonId}`);

  const position = page.getByTestId("change-position");
  await expect(position).toContainText("so far");

  await expect(page.getByTestId("block-loading-status")).toHaveAttribute(
    "data-state",
    "complete",
  );
  await expect(position).not.toContainText("so far");
});

test("a deep link past the first window survives and lands", async ({ page }) => {
  // The citation most worth sharing in a long manuscript is the one deepest
  // into it, which is exactly the link that used to be discarded.
  const target = totalBlocks - 5;
  expect(target).toBeGreaterThan(firstWindow);

  await withSlowWindowLoading(page);
  await gotoComparison(page, `/c/${comparisonId}?block=${target}`);

  // The parameter must still be there while the target is unloaded.
  await expect(page.getByTestId("block-loading-status")).toHaveAttribute(
    "data-state",
    "loading",
  );
  await expect(page).toHaveURL(new RegExp(`block=${target}`));

  await expect(page.getByTestId("block-loading-status")).toHaveAttribute(
    "data-state",
    "complete",
  );
  await expect(page).toHaveURL(new RegExp(`block=${target}`));
  await expect(page.getByTestId("change-position")).not.toContainText("so far");
});

test("navigation counts changes beyond the first window", async ({ page }) => {
  await gotoComparison(page, `/c/${comparisonId}`);
  await expect(page.getByTestId("block-loading-status")).toHaveAttribute(
    "data-state",
    "complete",
  );

  const label = await page.getByTestId("change-position").textContent();
  const counted = Number((label ?? "").match(/(\d+)\s+changed blocks/)?.[1] ?? "0");

  // More changes than the first window could possibly have contained, so this
  // can only be right if the later windows were loaded and counted.
  expect(counted).toBeGreaterThan(firstWindow / CHANGE_EVERY);
  expect(counted).toBeGreaterThan(10);
});
