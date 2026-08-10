import { promises as fs } from "node:fs";
import { test, expect } from "@playwright/test";
import { alteredA, alteredB } from "./helpers";

test("uploads two witnesses and renders a typography-first comparison", async ({
  page,
}, testInfo) => {
  const manuscriptAPath = testInfo.outputPath("tale-witness-a.txt");
  const manuscriptBPath = testInfo.outputPath("tale-witness-b.txt");
  await fs.writeFile(manuscriptAPath, alteredA, "utf-8");
  await fs.writeFile(manuscriptBPath, alteredB, "utf-8");

  await page.goto("/");
  await page.setInputFiles("#a-file", manuscriptAPath);
  await page.setInputFiles("#b-file", manuscriptBPath);

  const submit = page.getByRole("button", {
    name: "Compare Manuscript A and Manuscript B",
  });
  await expect(submit).toBeEnabled();
  await submit.click();

  await page.waitForURL(/\/c\/cmp_[^/?#]+$/);
  await expect(page).toHaveURL(/\/c\/cmp_[^/?#]+$/);

  await expect(page.getByTestId("diff-viewer")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Manuscript A" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Manuscript B" })).toBeVisible();
  await expect(page.getByTestId("token-INSERTION").first()).toBeVisible();
  await expect(page.getByTestId("token-DELETION").first()).toBeVisible();
  await expect(page.getByTestId("token-sign-INSERTION").first()).toHaveText("+");
  await expect(page.getByTestId("token-sign-DELETION").first()).toHaveText("\u2212");

  const summary = page.getByTestId("diff-summary-bar");
  await expect(summary).toBeVisible();
  await expect(summary).toContainText(/\d+% similar/);
});
