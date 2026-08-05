import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { createComparison, gotoComparison } from "./helpers";

const NAV_A =
  "The opening paragraph is shared by both witnesses.\n\n" +
  "The scribe kept the old phrase in the margin.\n\n" +
  "A second sentence remains plain and undecorated.\n\n" +
  "The final paragraph closes the manuscript quietly.";

const NAV_B =
  "The opening paragraph is shared by both witnesses.\n\n" +
  "The scribe kept the revised phrase in the margin.\n\n" +
  "A second sentence becomes ornate and decorated.\n\n" +
  "The final paragraph closes the manuscript with a flourish.";

function currentBlockParameter(page: Page) {
  return new URL(page.url()).searchParams.get("block");
}

test.describe("changed block navigation", () => {
  test("next and previous controls move the active block and replace ?block", async ({
    page,
    request,
  }) => {
    const comparisonId = await createComparison(request, NAV_A, NAV_B);

    await gotoComparison(page, `/c/${comparisonId}?view=unified`);
    // Visible is not the same as interactive: the viewer is server-rendered,
    // so a click can land before its handler exists.
    await expect(page.getByTestId("diff-viewer")).toHaveAttribute(
      "data-hydrated",
      "true",
    );
    await expect(page.getByTestId("change-navigator")).toBeVisible();

    await page.getByRole("button", { name: /next changed block/i }).click();
    await expect.poll(() => currentBlockParameter(page)).toBe("1");
    await expect(page.getByTestId("change-position")).toContainText("Change 1 of 3");

    await page.getByRole("button", { name: /next changed block/i }).click();
    await expect.poll(() => currentBlockParameter(page)).toBe("2");
    await expect(page.getByTestId("change-position")).toContainText("Change 2 of 3");

    await page.getByRole("button", { name: /previous changed block/i }).click();
    await expect.poll(() => currentBlockParameter(page)).toBe("1");
    await expect(page.getByTestId("change-position")).toContainText("Change 1 of 3");
  });

  test("deep links land on the requested block", async ({ page, request }) => {
    const comparisonId = await createComparison(request, NAV_A, NAV_B);

    await gotoComparison(page, `/c/${comparisonId}?view=unified&block=2`);

    await expect(page.getByTestId("change-position")).toContainText("Change 2 of 3");
    await expect.poll(() => currentBlockParameter(page)).toBe("2");
    await expect(page.locator(":focus")).toHaveAttribute(
      "data-testid",
      /diff-block-row-/,
    );
  });

  test("keyboard bindings work but ignore text entry", async ({ page, request }) => {
    const comparisonId = await createComparison(request, NAV_A, NAV_B);

    await gotoComparison(page, `/c/${comparisonId}?view=unified`);
    // The viewer is server-rendered, so it is on screen and looks ready before
    // its keyboard bindings exist. Pressing a key in that window loses the
    // keystroke with no error anywhere.
    await expect(page.getByTestId("diff-viewer")).toHaveAttribute(
      "data-hydrated",
      "true",
    );

    await page.keyboard.press("j");
    await expect.poll(() => currentBlockParameter(page)).toBe("1");

    await page.keyboard.press("n");
    await expect.poll(() => currentBlockParameter(page)).toBe("2");

    await page.keyboard.press("k");
    await expect.poll(() => currentBlockParameter(page)).toBe("1");

    await page.keyboard.press("p");
    await expect.poll(() => currentBlockParameter(page)).toBe("1");

    await page.evaluate(() => {
      const input = document.createElement("input");
      input.setAttribute("aria-label", "Navigation shortcut guard");
      document.body.append(input);
      input.focus();
    });
    await page.keyboard.press("n");
    await expect.poll(() => currentBlockParameter(page)).toBe("1");

    await page.locator("input[aria-label='Navigation shortcut guard']").blur();
    await page.keyboard.press("Escape");
    await expect.poll(() => currentBlockParameter(page)).toBeNull();
  });

  test("navigation controls have no automated wcag2a or wcag2aa violations", async ({
    page,
    request,
  }) => {
    const comparisonId = await createComparison(request, NAV_A, NAV_B);

    await gotoComparison(page, `/c/${comparisonId}?view=unified&block=2`);
    await expect(page.getByTestId("change-navigator")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    expect(
      results.violations,
      results.violations.map((violation) => violation.id).join(", "),
    ).toEqual([]);
  });
});
