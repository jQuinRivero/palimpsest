#!/usr/bin/env node
// Regenerate the documentation screenshots in _static.
//
// Server startup, teardown, and the seeded comparison live in dev_server.mjs,
// which capture_demo.mjs shares.
import { dirname, resolve } from "node:path";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import process from "node:process";

import playwright from "../frontend/node_modules/playwright/index.js";

import {
  createComparison,
  startApi,
  startWeb,
  stopChild,
  waitForViewer,
  webBase,
} from "./dev_server.mjs";

const { chromium } = playwright;
const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, "_static");

// A viewport screenshot rather than an element one. The diff viewer's header
// bar overflows its own box, so an element capture clips the export control on
// the right and the witness names on the left.
async function capture(page, name) {
  await page.screenshot({ path: resolve(outDir, name), animations: "disabled" });
}

const processes = [];
try {
  mkdirSync(outDir, { recursive: true });
  processes.push(await startApi());
  processes.push(await startWeb());

  const browser = await chromium.launch({
    channel: process.env.PALIMPSEST_DOCS_BROWSER ?? "msedge",
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  });

  await page.goto(webBase, { waitUntil: "networkidle" });
  await page.getByTestId("accepted-formats").waitFor({ state: "visible" });
  await capture(page, "uploader.png");

  const comparisonId = await createComparison();
  await page.setViewportSize({ width: 1280, height: 1150 });
  await page.goto(`${webBase}/c/${comparisonId}?view=synoptic`, { waitUntil: "networkidle" });
  await waitForViewer(page);
  await capture(page, "synoptic-view.png");

  await page.goto(`${webBase}/c/${comparisonId}?view=unified`, { waitUntil: "networkidle" });
  await waitForViewer(page);
  await capture(page, "unified-view.png");

  await browser.close();
} finally {
  for (const child of processes.filter(Boolean).reverse()) {
    await stopChild(child);
  }
}
