import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { chooseWitnessFile, createComparison, gotoComparison } from "./helpers";

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

test("a refused witness has no automated wcag2a or wcag2aa violations", async ({ page }) => {
  // The error state is the one most likely to fail contrast: it is the only
  // surface that puts text on the deletion underlay and pairs it with a
  // muted-on-tinted code line. It is also the state a researcher is least
  // able to skip past, and it had no axe coverage despite the testing
  // strategy naming error states explicitly.
  await chooseWitnessFile(page, {
    name: "photograph.png",
    mimeType: "image/png",
    buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10]),
  });

  await expect(page.getByTestId("manuscript-uploader")).toContainText("UNSUPPORTED_FORMAT");
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
