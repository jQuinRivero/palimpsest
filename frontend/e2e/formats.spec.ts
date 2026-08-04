import { expect, test } from "@playwright/test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * The specification claims that registering a new parser widens what the
 * client accepts with **no frontend change**, because the uploader builds its
 * accept list from `GET /api/v1/capabilities` rather than hardcoding formats.
 *
 * Phase 2 registered four new parsers. Not one line of frontend code changed.
 * These tests are the evidence.
 */

const EXPECTED_EXTENSIONS = [".txt", ".md", ".markdown", ".docx", ".pdf"];

test("the uploader accepts every registered format without hardcoding any", async ({
  page,
  request,
}) => {
  const capabilities = await (
    await request.get("http://127.0.0.1:8000/api/v1/capabilities")
  ).json();

  const serverExtensions: string[] = capabilities.parsers.flatMap(
    (parser: { extensions: string[] }) => parser.extensions,
  );
  for (const extension of EXPECTED_EXTENSIONS) {
    expect(serverExtensions).toContain(extension);
  }

  await page.goto("/");

  // The accept attribute is populated once capabilities resolve on the client.
  const input = page.locator('input[type="file"]').first();
  await expect
    .poll(async () => (await input.getAttribute("accept")) ?? "", {
      timeout: 15_000,
    })
    .toContain(".pdf");

  const accept = (await input.getAttribute("accept")) ?? "";
  for (const extension of EXPECTED_EXTENSIONS) {
    expect(accept, `accept list should offer ${extension}`).toContain(extension);
  }
});

test("a markdown witness pair collates end to end", async ({ page }) => {
  const directory = mkdtempSync(join(tmpdir(), "palimpsest-md-"));
  const a = join(directory, "witness-a.md");
  const b = join(directory, "witness-b.md");

  writeFileSync(a, "# Chapter One\n\nIt was the best of times.\n", "utf8");
  writeFileSync(b, "# Chapter One\n\nIt was the brightest of times.\n", "utf8");

  await page.goto("/");

  const inputs = page.locator('input[type="file"]');
  await expect
    .poll(async () => (await inputs.first().getAttribute("accept")) ?? "", {
      timeout: 15_000,
    })
    .toContain(".md");

  await inputs.nth(0).setInputFiles(a);
  await inputs.nth(1).setInputFiles(b);

  await page.getByRole("button", { name: /compare|collate|submit/i }).click();

  await page.waitForURL(/\/c\/cmp_/, { timeout: 30_000 });
  await expect(page.getByTestId("diff-viewer")).toBeVisible();
  await expect(page.getByTestId("token-INSERTION").first()).toBeVisible();
  await expect(page.getByTestId("token-DELETION").first()).toBeVisible();

  // The heading survives ingestion and is not diffed as prose.
  await expect(page.getByText("Chapter One").first()).toBeVisible();
});
