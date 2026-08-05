import { expect, test } from "@playwright/test";
import { gotoComparison } from "./helpers";
import AxeBuilder from "@axe-core/playwright";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * TEI export, end to end.
 *
 * These assert the downloaded bytes rather than the presence of a link. A
 * download affordance that produces the wrong file, or no file, looks
 * identical in the DOM to one that works.
 */

const API = "http://127.0.0.1:8000";

const A = "It was a long crossing. The waves were grey.\n\nAlpha stands first.\n";
const B = "It was a long crossing.\n\nThe waves were slate.\n\nAlpha stands first.\n";

async function comparisonFor(
  request: import("@playwright/test").APIRequestContext,
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
      a_document_id: await upload(A, "a.txt"),
      b_document_id: await upload(B, "b.txt"),
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  return (await created.json()).comparison_id as string;
}

test("the export control downloads a TEI file naming both witnesses", async ({
  page,
  request,
}) => {
  const id = await comparisonFor(request);
  await gotoComparison(page, `/c/${id}`);

  const control = page.getByTestId("export-tei");
  await expect(control).toBeVisible();

  const [download] = await Promise.all([page.waitForEvent("download"), control.click()]);

  expect(download.suggestedFilename()).toContain(id);
  expect(download.suggestedFilename()).toMatch(/\.xml$/);

  const directory = mkdtempSync(join(tmpdir(), "palimpsest-tei-"));
  const path = join(directory, download.suggestedFilename());
  await download.saveAs(path);
  const xml = readFileSync(path, "utf8");

  // A real TEI document, not an error page that happened to download.
  expect(xml).toContain('<?xml version="1.0" encoding="UTF-8"?>');
  expect(xml).toContain('xmlns="http://www.tei-c.org/ns/1.0"');
  expect(xml).toContain('method="parallel-segmentation"');
  expect(xml).toContain('<witness xml:id="A">');
  expect(xml).toContain('<witness xml:id="B">');

  // The collation itself, including the structural finding a plain diff
  // would have reported as a rewrite.
  expect(xml).toContain('<rdg wit="#A">');
  expect(xml).toContain('<rdg wit="#B">');
  expect(xml).toContain('<linkGrp type="split">');
});

test("the exported file parses as XML in the browser", async ({ page, request }) => {
  const id = await comparisonFor(request);
  // Navigate first so the fetch runs from the application's own origin. That
  // makes this a CORS check as well as a well-formedness one: a third-party
  // tool reading the export from a browser needs both to hold.
  await gotoComparison(page, `/c/${id}`);

  // DOMParser is the cheapest honest well-formedness check available here,
  // and it runs on the bytes the endpoint actually served.
  const result = await page.evaluate(async (url) => {
    const response = await fetch(url);
    const text = await response.text();
    const parsed = new DOMParser().parseFromString(text, "application/xml");
    const error = parsed.querySelector("parsererror");
    return {
      contentType: response.headers.get("content-type"),
      error: error ? error.textContent : null,
      root: parsed.documentElement.tagName,
      blocks: parsed.getElementsByTagName("p").length,
    };
  }, `${API}/api/v1/comparisons/${id}/export/tei`);

  expect(result.error).toBeNull();
  expect(result.contentType).toContain("application/tei+xml");
  expect(result.root).toBe("TEI");
  expect(result.blocks).toBeGreaterThan(0);
});

test("the export control has no accessibility violations", async ({ page, request }) => {
  const id = await comparisonFor(request);
  await gotoComparison(page, `/c/${id}`);
  await expect(page.getByTestId("export-tei")).toBeVisible();

  const results = await new AxeBuilder({ page })
    .include('[data-testid="export-tei"]')
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();

  expect(
    results.violations,
    results.violations.map((v) => `${v.id} (${v.nodes.length})`).join(", "),
  ).toEqual([]);
});
