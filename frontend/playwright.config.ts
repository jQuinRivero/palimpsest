import { defineConfig, devices } from "@playwright/test";

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
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: true,
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
