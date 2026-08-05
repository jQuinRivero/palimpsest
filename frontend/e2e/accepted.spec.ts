import { expect, test } from "@playwright/test";
import { gotoComparison } from "./helpers";

/**
 * The accepted-and-poll path, which is what "100k+ words" actually means.
 *
 * A comparison above the server's inline budget returns `202` with a
 * `ComparisonAccepted` body — no blocks, no metrics — and is computed in the
 * background. `202` is a success status, so a client checking only
 * `response.ok` receives that body while believing it holds a
 * `ComparisonResult`.
 *
 * That is exactly what happened: uploading two large manuscripts ended at an
 * HTTP 500 reading "Cannot read properties of undefined (reading 'length')".
 * The backend was correct throughout; the client had never been taught that
 * `202` exists. These tests exist so it stays taught.
 */

const API = "http://127.0.0.1:8000";

/**
 * Above `inline_blocks_per_comparison` (4,000 combined), so the server
 * accepts the comparison rather than computing it inline. Large enough that
 * the background collation is still running when a page load reaches the
 * server, which is what makes the pending view observable rather than a
 * race — collation of this fixture takes roughly a second.
 */
const BLOCKS = 5000;

function witness(revised: boolean): string {
  const paragraphs: string[] = [];
  for (let i = 0; i < BLOCKS; i += 1) {
    paragraphs.push(
      revised && i % 500 === 0
        ? `Paragraph ${i} revised with different wording entirely here.`
        : `Paragraph ${i} of the witness carrying enough words to be real.`,
    );
  }
  return paragraphs.join("\n\n");
}

async function uploadPair(request: import("@playwright/test").APIRequestContext) {
  const upload = async (text: string, name: string) => {
    const response = await request.post(`${API}/api/v1/documents`, {
      multipart: {
        file: { name, mimeType: "text/plain", buffer: Buffer.from(text, "utf8") },
      },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    return (await response.json()).id as string;
  };

  return {
    a: await upload(witness(false), "accepted-a.txt"),
    b: await upload(witness(true), "accepted-b.txt"),
  };
}

test("an oversized comparison is accepted rather than computed inline", async ({
  request,
}) => {
  const { a, b } = await uploadPair(request);

  const created = await request.post(`${API}/api/v1/comparisons`, {
    data: { a_document_id: a, b_document_id: b },
  });

  // The premise of everything below. If the budget ever rises past this
  // fixture, these tests would otherwise keep passing while exercising the
  // ordinary inline path.
  expect(
    created.status(),
    "fixture must exceed the inline budget; see app/config.py",
  ).toBe(202);

  const body = await created.json();
  expect(body.status).toBe("PENDING");
  expect(body).not.toHaveProperty("blocks");
});

test("a pending comparison renders a waiting page, not an error", async ({
  page,
  request,
}) => {
  const { a, b } = await uploadPair(request);
  const created = await request.post(`${API}/api/v1/comparisons`, {
    data: { a_document_id: a, b_document_id: b },
  });
  const id = (await created.json()).comparison_id as string;

  // Immediately, while the background collation is still running.
  const response = await page.goto(`/c/${id}`);

  // The regression, stated as an assertion: this used to be a 500.
  expect(response?.status()).toBe(200);

  const pending = page.getByTestId("comparison-pending");
  await expect(pending).toBeVisible();
  await expect(pending).toHaveAttribute("data-state", "waiting");
  // Copy that does not promise a time the server cannot predict.
  await expect(pending).toContainText(/still collating/i);
});

test("the waiting page becomes the comparison without being reloaded", async ({
  page,
  request,
}) => {
  const { a, b } = await uploadPair(request);
  const created = await request.post(`${API}/api/v1/comparisons`, {
    data: { a_document_id: a, b_document_id: b },
  });
  const id = (await created.json()).comparison_id as string;

  await page.goto(`/c/${id}`);
  await expect(page.getByTestId("comparison-pending")).toBeVisible();

  // The reader does nothing; the page polls and then shows the collation.
  await expect(page.getByTestId("diff-viewer")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("comparison-pending")).toHaveCount(0);
});

test("uploading two large manuscripts ends at a rendered comparison", async ({
  page,
  request,
}) => {
  // The whole path a researcher actually takes, rather than its parts.
  const { a, b } = await uploadPair(request);
  const created = await request.post(`${API}/api/v1/comparisons`, {
    data: { a_document_id: a, b_document_id: b },
  });
  expect(created.status()).toBe(202);
  const id = (await created.json()).comparison_id as string;

  await gotoComparison(page, `/c/${id}`);

  await expect(page.getByTestId("diff-summary-bar")).toBeVisible();
  const label = await page.getByTestId("change-position").textContent();
  expect(label).toMatch(/changed blocks/);
});
