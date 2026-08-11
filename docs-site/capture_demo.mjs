#!/usr/bin/env node
// Record the README demo: docs-site/_static/demo.gif.
//
// A still screenshot cannot show the one thing that distinguishes this tool --
// that structural change and wording change are reported as different kinds of
// thing, and that the same comparison can be read as two columns or as one
// stream. A short loop does, and it is the asset that does the most work on a
// repository page and in a social post.
//
// One frame per state with an explicit duration, rather than a frame rate.
// Timing here is reading time, which differs per panel, and a fixed rate would
// mean padding with duplicate frames. public_release_audit.py fails any blob
// over 1 MB, so a committed demo has to earn every frame.
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
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
const output = resolve(outDir, "demo.gif");

// Captured at reading width and scaled at encode time, so text is resampled
// rather than rendered small. The short viewport keeps the frame full of text
// instead of the empty page below a short comparison.
const VIEWPORT = { width: 1280, height: 660 };
const GIF_WIDTH = 900;

// A constant rate with repeated frames, rather than per-frame durations. The
// concat demuxer's `duration` directive does not survive into the GIF muxer --
// every delay comes out as 40 ms however it is combined with -fps_mode -- so
// timing is expressed the only way the format reliably carries it. Repeats are
// nearly free: consecutive identical frames encode as an empty delta.
const FPS = 2;

const ffmpeg = process.env.FFMPEG ?? "ffmpeg";

const frames = [];

// Scroll by element rather than by pixel offset: the panels move whenever the
// summary text rewraps, and a hard-coded offset silently starts framing the
// wrong thing.
async function anchor(page, testId, block = "start") {
  await page.evaluate(
    ([id, position]) => {
      document
        .querySelector(`[data-testid="${id}"]`)
        ?.scrollIntoView({ behavior: "instant", block: position });
    },
    [testId, block],
  );
  await page.waitForTimeout(150);
}

function frameName(index) {
  return `frame-${String(index).padStart(3, "0")}.png`;
}

async function shot(page, dir, seconds) {
  const first = frameName(frames.length);
  await page.screenshot({ path: resolve(dir, first), animations: "disabled" });
  frames.push(first);

  for (let i = 1; i < Math.round(seconds * FPS); i += 1) {
    const repeat = frameName(frames.length);
    copyFileSync(resolve(dir, first), resolve(dir, repeat));
    frames.push(repeat);
  }
}

const processes = [];
// Set PALIMPSEST_DEMO_FRAMES to keep the intermediate PNGs. Assembling a GIF
// hides which step went wrong: a bad capture and a bad encode both look like a
// bad GIF, and only the raw frames tell them apart.
const keepFrames = process.env.PALIMPSEST_DEMO_FRAMES;
const workDir = keepFrames ?? mkdtempSync(resolve(tmpdir(), "palimpsest-demo-"));
try {
  mkdirSync(outDir, { recursive: true });
  processes.push(await startApi());
  processes.push(await startWeb());

  const browser = await chromium.launch({
    channel: process.env.PALIMPSEST_DOCS_BROWSER ?? "msedge",
    headless: true,
  });
  const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });

  // 1. Where you start: two manuscripts, nothing compared yet.
  await page.goto(webBase, { waitUntil: "networkidle" });
  await page.getByTestId("accepted-formats").waitFor({ state: "visible" });
  await shot(page, workDir, 2.2);

  const comparisonId = await createComparison();

  // 2. The verdict: how similar, how many words changed, and -- separately --
  //    what happened structurally.
  await page.goto(`${webBase}/c/${comparisonId}?view=synoptic`, { waitUntil: "networkidle" });
  await waitForViewer(page);
  await shot(page, workDir, 2.6);

  await anchor(page, "structural-summary");
  await shot(page, workDir, 2.6);

  // 3. Each witness in its own order, so a move is visible as a move.
  await anchor(page, "source-order-overview");
  await shot(page, workDir, 2.6);

  // 4. The aligned reading, where the one genuinely changed word appears.
  await anchor(page, "synoptic-scroller", "center");
  await shot(page, workDir, 3.0);

  // 5. The same comparison as a single stream.
  await page.goto(`${webBase}/c/${comparisonId}?view=unified`, { waitUntil: "networkidle" });
  await waitForViewer(page);
  await shot(page, workDir, 2.6);

  await anchor(page, "unified-view", "center");
  await shot(page, workDir, 3.0);

  await browser.close();

  // A palette generated across the whole sequence rather than per frame: this
  // artwork is flat colour and thin serif text, which dithers badly against a
  // guessed palette. Bayer dithering keeps flat areas from developing noise,
  // which also keeps the file small.
  //
  // Two passes, writing the palette to a file, rather than one pass with
  // split/palettegen/paletteuse: palettegen emits a single frame, and rejoining
  // that with the image sequence collapses the output to one repeated frame.
  // Two passes is also what the ffmpeg GIF documentation shows.
  const scale = `scale=${GIF_WIDTH}:-1:flags=lanczos`;
  const input = ["-framerate", String(FPS), "-i", "frame-%03d.png"];

  execFileSync(
    ffmpeg,
    [
      "-y",
      "-loglevel", "error",
      ...input,
      "-vf", `${scale},palettegen=max_colors=192:stats_mode=full`,
      "palette.png",
    ],
    { cwd: workDir, stdio: "inherit" },
  );

  execFileSync(
    ffmpeg,
    [
      "-y",
      "-loglevel", "error",
      ...input,
      "-i", "palette.png",
      "-lavfi", `${scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4`,
      "-loop", "0",
      output,
    ],
    { cwd: workDir, stdio: "inherit" },
  );

  console.log(`wrote ${output} from ${frames.length} frames at ${FPS} fps`);
} finally {
  if (!keepFrames) rmSync(workDir, { recursive: true, force: true });
  for (const child of processes.filter(Boolean).reverse()) {
    await stopChild(child);
  }
}
