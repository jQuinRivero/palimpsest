import { expect, test } from "@playwright/test";
import { E2E_BLOCK_PAGE_LIMIT } from "../playwright.config";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

/**
 * Refuse to run against an API that is not configured for this suite.
 *
 * `webServer.reuseExistingServer` is true for the API, which is what makes
 * iterating pleasant: leave uvicorn running and the suite starts instantly.
 * The cost is that an API started any other way is adopted silently, including
 * one started the way the README documents:
 *
 *     cd backend && uv run uvicorn app.main:app --reload
 *
 * That server has production limits, so `windowing.spec` builds a fixture it
 * believes is oversized, receives an untruncated payload, and fails its own
 * premise. The message it prints — "fixture must be large enough to be
 * windowed; see playwright.config.ts" — sends the reader to a file where the
 * value is set correctly, because the problem is not the config but which
 * process is answering.
 *
 * So check it once, up front, and say the thing that is actually wrong.
 * `default_block_page_limit` is the sentinel: it is the only one of the three
 * E2E settings the API reports, and nothing but this suite sets it to 10.
 */
test("the API under test is configured for this suite", async ({ request }) => {
  const response = await request.get(`${API_BASE}/api/v1/capabilities`);
  expect(response.ok(), `no API answering at ${API_BASE}`).toBeTruthy();

  const capabilities = await response.json();

  expect(
    capabilities.default_block_page_limit,
    [
      `The API at ${API_BASE} was not started by Playwright.`,
      "",
      "It reports default_block_page_limit=" +
        `${capabilities.default_block_page_limit}, but this suite needs ` +
        `${E2E_BLOCK_PAGE_LIMIT}. Playwright reuses an API that is already ` +
        "running, so a server started by hand — as the README's quickstart " +
        "does — is adopted with production limits, and the windowing tests " +
        "fail on a premise that has nothing to do with your change.",
      "",
      "Stop that server and run the suite again, or restart it with the",
      "environment in playwright.config.ts (E2E_API_ENV).",
    ].join("\n"),
  ).toBe(E2E_BLOCK_PAGE_LIMIT);
});
