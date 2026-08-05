import { expect, type APIRequestContext, type Page } from "@playwright/test";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export const alteredA =
  "It was the best of times, it was the worst of times.\n\n" +
  "It was the age of wisdom, it was the age of foolishness.\n\n" +
  "We had everything before us, we had nothing before us.";

export const alteredB =
  "It was the best of times, it was the strangest of times.\n\n" +
  "It was the age of wisdom, it was the bright age of foolishness.\n\n" +
  "We had everything before us, we had little before us.";

export const identicalWitness =
  "It was the best of times, it was the worst of times.\n\n" +
  "It was the age of wisdom, it was the age of foolishness.";

type DocumentSummary = {
  id: string;
};

type ComparisonResult = {
  comparison_id: string;
};

export async function uploadText(
  request: APIRequestContext,
  title: string,
  text: string,
): Promise<DocumentSummary> {
  const response = await request.post(`${API_BASE}/api/v1/documents`, {
    multipart: {
      title,
      file: {
        name: `${title}.txt`,
        mimeType: "text/plain",
        buffer: Buffer.from(text, "utf-8"),
      },
    },
  });

  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()) as DocumentSummary;
}

export async function createComparison(
  request: APIRequestContext,
  aText = alteredA,
  bText = alteredB,
): Promise<string> {
  const a = await uploadText(request, "Manuscript A", aText);
  const b = await uploadText(request, "Manuscript B", bText);

  const response = await request.post(`${API_BASE}/api/v1/comparisons`, {
    data: {
      a_document_id: a.id,
      b_document_id: b.id,
    },
  });

  expect(response.ok(), await response.text()).toBeTruthy();
  const comparison = (await response.json()) as ComparisonResult;
  return comparison.comparison_id;
}

/**
 * Navigate to a comparison and wait until the viewer can actually respond.
 *
 * The page is server-rendered, so the reading surface, the toggles and the
 * navigator are all on screen — and inert — before React attaches anything to
 * them. A click or a keypress in that window is discarded with no error, which
 * surfaces as a test that passes alone and fails in a full run, on a different
 * assertion each time.
 *
 * Waiting on visibility is not enough for the same reason: the markup being
 * present is precisely what makes the gap invisible. `data-hydrated` is set by
 * `DiffViewer` in an effect, so it appears only once the handlers exist.
 */
export async function gotoComparison(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByTestId("diff-viewer")).toHaveAttribute("data-hydrated", "true");
}
