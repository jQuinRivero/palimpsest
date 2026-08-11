#!/usr/bin/env node
// Render scripts/social-preview.html to docs-site/_static/social-preview.png.
//
// GitHub, Mastodon, Bluesky, and Slack all show this image when the repository
// or the guide is linked. Without one they show a generic avatar, which is a
// wasted impression in the only moment a stranger is deciding whether to look.
//
// 1280x640 is GitHub's recommended social-preview size and satisfies the
// og:image and twitter:summary_large_image minimums.
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import process from "node:process";

import playwright from "../frontend/node_modules/playwright/index.js";

const { chromium } = playwright;
const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..");

const source = resolve(here, "social-preview.html");
const output = resolve(repo, "docs-site", "_static", "social-preview.png");

const browser = await chromium.launch({
  channel: process.env.PALIMPSEST_DOCS_BROWSER ?? "msedge",
  headless: true,
});
try {
  const page = await browser.newPage({
    viewport: { width: 1280, height: 640 },
    deviceScaleFactor: 1,
  });
  await page.goto(pathToFileURL(source).href, { waitUntil: "networkidle" });
  // Fonts resolve from the system, so a screenshot taken before they settle
  // silently ships a fallback face.
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: output, animations: "disabled" });
  console.log(`wrote ${output}`);
} finally {
  await browser.close();
}
