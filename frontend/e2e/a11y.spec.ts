import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { createComparison, gotoComparison } from "./helpers";

async function expectNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();

  expect(results.violations).toEqual([]);
}

test("upload page has no automated wcag2a or wcag2aa violations", async ({ page }) => {
  await page.goto("/");

  await expectNoA11yViolations(page);
});

test("comparison page has no automated wcag2a or wcag2aa violations in both reading modes", async ({
  page,
  request,
}) => {
  const comparisonId = await createComparison(request);

  await gotoComparison(page, `/c/${comparisonId}`);
  await expect(page.locator('[data-testid="diff-viewer"][data-view="synoptic"]')).toBeVisible();
  await expectNoA11yViolations(page);

  await gotoComparison(page, `/c/${comparisonId}?view=unified`);
  await expect(page.locator('[data-testid="diff-viewer"][data-view="unified"]')).toBeVisible();
  await expectNoA11yViolations(page);
});
