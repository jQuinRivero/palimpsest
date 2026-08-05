import { test, expect } from "@playwright/test";
import { createComparison, gotoComparison, identicalWitness } from "./helpers";

test("switches reading modes and honors unified deep links", async ({ page, request }) => {
  const comparisonId = await createComparison(request);

  await gotoComparison(page, `/c/${comparisonId}`);
  await expect(page.locator('[data-testid="diff-viewer"][data-view="synoptic"]')).toBeVisible();

  await page.getByRole("button", { name: "unified" }).click();
  await expect(page.locator('[data-testid="diff-viewer"][data-view="unified"]')).toBeVisible();

  await gotoComparison(page, `/c/${comparisonId}?view=unified`);
  await expect(page.locator('[data-testid="diff-viewer"][data-view="unified"]')).toBeVisible();
});

test("summarizes identical witnesses without wording changes", async ({ page, request }) => {
  const comparisonId = await createComparison(request, identicalWitness, identicalWitness);

  await gotoComparison(page, `/c/${comparisonId}`);

  await expect(page.getByTestId("diff-summary-bar")).toContainText("No wording changes");
});

test("unknown comparison ids return HTTP 404", async ({ page }) => {
  const response = await page.goto("/c/cmp_doesnotexist");

  expect(response?.status()).toBe(404);
});
