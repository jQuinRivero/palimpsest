import { defineConfig, devices } from "@playwright/test";
import os from "node:os";

/**
 * Parallelism is capped rather than left to the default.
 *
 * The suite contains genuinely heavy tests — printing a three-hundred-block
 * comparison renders every row unvirtualized in the browser — and they run
 * against a single-process API. Saturating the machine starves whichever
 * worker happens to be waiting on a UI assertion, which surfaces as a
 * different unrelated test timing out on each run rather than as anything
 * that points at the real cause. Measured at the default six workers: one
 * failure in six runs. At three: none in five.
 *
 * The cap keeps Playwright's own core-based heuristic, so a small CI runner
 * still gets fewer workers than this ceiling rather than more.
 */
const workers = Math.max(1, Math.min(3, Math.floor(os.cpus().length / 2)));

/**
 * The window threshold is lowered for end-to-end runs so that `windowing.spec`
 * can drive a truncated comparison with about thirty blocks instead of the
 * three thousand the production default would demand.
 *
 * This is the same technique as testing pagination with a page size of two.
 * What is under test is the client's response to `truncated: true`, which does
 * not depend on the absolute size; whereas building a genuinely oversized
 * comparison costs seconds of CPU in the API process and starves every other
 * test running beside it. Real comparisons in the rest of the suite are a
 * handful of blocks and stay well under this threshold, so nothing else sees
 * a windowed payload.
 *
 * CI starts the API itself, so it must set the same value — see ci.yml.
 */
export const E2E_WINDOW_BLOCK_THRESHOLD = 25;

const E2E_API_ENV = {
  PALIMPSEST_COMPARISON_WINDOW_BLOCK_THRESHOLD: String(E2E_WINDOW_BLOCK_THRESHOLD),
  PALIMPSEST_DEFAULT_BLOCK_PAGE_LIMIT: "10",
  // The whole suite arrives from one client address in bursts, which is
  // precisely the traffic shape the limiter exists to reject. A throttled
  // upload fails a fixture in milliseconds and reads as an unrelated
  // assertion failing, so the suite spends its time diagnosing itself.
  // Nothing is lost: the limiter has its own integration test, and the other
  // integration tests already disable it.
  PALIMPSEST_RATE_LIMIT_ENABLED: "false",
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: true,
  workers,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      // `cwd` rather than a `cd` in the command: CI runs on Linux and a
      // Windows-style path would not resolve there.
      command: "uv run uvicorn app.main:app --port 8000",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/v1/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: E2E_API_ENV,
    },
    {
      // CI builds first, so serve the production output there; locally the dev
      // server is more convenient.
      command: process.env.CI ? "npm run start" : "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
