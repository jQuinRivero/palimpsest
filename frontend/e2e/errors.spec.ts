import { expect, test } from "@playwright/test";
import { buildScannedPdf } from "./pdf";

/**
 * What a researcher is told when something is wrong.
 *
 * The API's error taxonomy is covered by backend tests. None of it had ever
 * been checked from the browser, which is where it matters: the accepted-path
 * bug that returned a 500 for large manuscripts was exactly this shape — the
 * server answering correctly and the client saying nothing useful.
 *
 * These assert the reader's experience, not the status code.
 */

const UPLOADER = '[data-testid="manuscript-uploader"]';

async function chooseFile(
  page: import("@playwright/test").Page,
  file: { name: string; mimeType: string; buffer: Buffer },
) {
  await page.goto("/");
  await expect(page.locator(UPLOADER)).toBeVisible();
  // Wait for capabilities. Without this the local pre-check may or may not
  // have run by the time the file is chosen, so a test meaning to exercise
  // the local path would silently exercise the server's instead.
  await expect(page.getByTestId("accepted-formats")).toBeVisible();
  await page.locator('input[type="file"]').first().setInputFiles(file);
}

test("the accepted formats are written for a person", async ({ page }) => {
  await page.goto("/");

  const line = page.getByTestId("accepted-formats");
  await expect(line).toBeVisible();

  const text = (await line.textContent()) ?? "";

  // This sentence used to be the `accept` attribute rendered as prose, which
  // put "application/vnd.openxmlformats-officedocument.wordprocessingml.
  // document" in front of a reader before they had done anything.
  expect(text).not.toContain("application/");
  expect(text).not.toContain("text/plain");
  expect(text).toMatch(/plain text/i);
  expect(text).toMatch(/word/i);
  expect(text).toMatch(/25 MB/i);

  // One entry per format, not one per parser: two parsers read PDF.
  expect(text.match(/PDF/gi)?.length).toBe(1);
});

test("an unsupported file is refused in words, not just in a code", async ({ page }) => {
  await chooseFile(page, {
    name: "photograph.png",
    mimeType: "image/png",
    buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10]),
  });

  const uploader = page.locator(UPLOADER);
  await expect(uploader).toContainText(/unsupported format/i);
  // Names the file, so a researcher uploading two knows which one failed.
  // This must hold whether the local pre-check or the server refused, and
  // which of those answers is a race whenever capabilities are slow.
  await expect(uploader).toContainText("photograph.png");
  // And keeps the code, which is what they would quote in a bug report.
  await expect(uploader).toContainText("UNSUPPORTED_FORMAT");
});

test("the server's refusal names the file too", async ({ page }) => {
  // The counterpart to the test above. With capabilities slow, the local
  // pre-check is skipped and the server answers instead — and its message is
  // deliberately about parsers ("No registered parser matched declared media
  // type, file extension, or magic bytes"), not about this upload. The card
  // has to supply what the message cannot, or the researcher is told a file
  // was rejected without being told which.
  await page.route("**/api/v1/capabilities", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 3000));
    await route.continue();
  });

  await page.goto("/");
  await expect(page.locator(UPLOADER)).toBeVisible();
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "photograph.png",
    mimeType: "image/png",
    buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10]),
  });

  const uploader = page.locator(UPLOADER);
  await expect(uploader).toContainText("UNSUPPORTED_FORMAT");
  await expect(uploader).toContainText("photograph.png");
});

test("an empty witness is refused", async ({ page }) => {
  await chooseFile(page, {
    name: "blank.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("   \n  \n"),
  });

  await expect(page.locator(UPLOADER)).toContainText(/empty/i);
});

test("a scanned PDF is refused honestly rather than read as blank", async ({ page }) => {
  // The product's most deliberate refusal: OCR does not ship, and returning
  // an empty document for a file the researcher can plainly read would be a
  // silent lie.
  const scanned = buildScannedPdf(2);

  await chooseFile(page, {
    name: "scanned.pdf",
    mimeType: "application/pdf",
    buffer: scanned,
  });

  const uploader = page.locator(UPLOADER);
  await expect(uploader).toContainText("OCR_REQUIRED");
  // The message must say what is wrong with the file, not merely that
  // something is.
  await expect(uploader).toContainText(/scan|image|text layer|OCR/i);
});

test("a refusal is announced, not only shown", async ({ page }) => {
  await chooseFile(page, {
    name: "photograph.png",
    mimeType: "image/png",
    buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10]),
  });

  // A reader who cannot see the panel still has to learn the upload failed.
  // The panel itself carries aria-live, so this must target the screen-reader
  // region: the point is that the announcement is self-contained, naming both
  // the witness and the file rather than relying on visible layout.
  const announcement = page.locator(".sr-only[aria-live]", { hasText: /has an error/i }).first();
  await expect(announcement).toContainText(/Manuscript A has an error/i);
  await expect(announcement).toContainText("photograph.png");
});

test("a file chosen before the format list arrives is still uploaded", async ({ page }) => {
  // The local format check is a courtesy; the server is the authority. When
  // capabilities are slow, refusing here called a good manuscript an
  // UNSUPPORTED_FORMAT — which is not knowable yet — and discarded it, so the
  // researcher had to choose the file again.
  await page.route("**/api/v1/capabilities", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 3000));
    await route.continue();
  });

  await page.goto("/");
  await expect(page.locator(UPLOADER)).toBeVisible();

  await page.locator('input[type="file"]').first().setInputFiles({
    name: "witness.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("It was the best of times."),
  });

  const uploader = page.locator(UPLOADER);
  await expect(uploader).not.toContainText(/still loading/i);
  await expect(uploader).toContainText("witness.txt");
  // Accepted by the server, which is the only thing that can actually say so.
  await expect(uploader).not.toContainText("UNSUPPORTED_FORMAT");
});
