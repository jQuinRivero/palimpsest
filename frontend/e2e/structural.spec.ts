import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import type { ComparisonResult, DiffBlock } from "@/lib/types";

function token(text: string) {
  return { text, status: "UNCHANGED" as const };
}

const metrics = {
  similarity: 1,
  edit_count: 0,
  insertions: 0,
  deletions: 0,
  unchanged_tokens: 6,
  churn: 0,
};

const blocks: DiffBlock[] = [
  {
    id: "moved-pair",
    status: "MOVED",
    kind: "PARAGRAPH",
    a_index: 0,
    b_index: 2,
    a_block_id: "a-moved",
    b_block_id: "b-moved",
    tokens: [token("The moonlit abbey returned after the storm.")],
    a_tokens: [token("The moonlit abbey returned after the storm.")],
    b_tokens: [token("The moonlit abbey returned after the storm.")],
    metrics,
    move_distance: 2,
    group_id: "move-abbey",
  },
  {
    id: "split-source",
    status: "SPLIT",
    kind: "PARAGRAPH",
    a_index: 1,
    b_index: 0,
    a_block_id: "a-split",
    b_block_id: "b-split-1",
    tokens: [token("First the bell answered. Then the village woke.")],
    a_tokens: [token("First the bell answered. Then the village woke.")],
    b_tokens: [token("First the bell answered.")],
    metrics,
    move_distance: null,
    group_id: "split-bell",
  },
  {
    id: "split-target",
    status: "SPLIT",
    kind: "PARAGRAPH",
    a_index: 1,
    b_index: 1,
    a_block_id: "a-split",
    b_block_id: "b-split-2",
    tokens: [token("Then the village woke.")],
    a_tokens: [],
    b_tokens: [token("Then the village woke.")],
    metrics,
    move_distance: null,
    group_id: "split-bell",
  },
  {
    id: "merge-source",
    status: "MERGED",
    kind: "PARAGRAPH",
    a_index: 2,
    b_index: 3,
    a_block_id: "a-merge-1",
    b_block_id: "b-merge",
    tokens: [token("The scribe paused and trimmed the wick.")],
    a_tokens: [token("The scribe paused.")],
    b_tokens: [token("The scribe paused and trimmed the wick.")],
    metrics,
    move_distance: null,
    group_id: "merge-scribe",
  },
  {
    id: "merge-source-two",
    status: "MERGED",
    kind: "PARAGRAPH",
    a_index: 3,
    b_index: 3,
    a_block_id: "a-merge-2",
    b_block_id: "b-merge",
    tokens: [token("The scribe paused and trimmed the wick.")],
    a_tokens: [token("And trimmed the wick.")],
    b_tokens: [],
    metrics,
    move_distance: null,
    group_id: "merge-scribe",
  },
];

const comparison: ComparisonResult = {
  comparison_id: "structural-fixture",
  created_at: "2026-08-04T16:48:01.324Z",
  expires_at: "2026-08-05T16:48:01.324Z",
  a: {
    id: "doc-a",
    title: "Manuscript A",
    source_format: "TXT",
    metadata: {
      word_count: 24,
      block_count: 4,
      char_count: 160,
      detected_language: "en",
      parser_name: "fixture",
      parser_version: "1.0.0",
      ocr_confidence: null,
    },
    warnings: [],
  },
  b: {
    id: "doc-b",
    title: "Manuscript B",
    source_format: "TXT",
    metadata: {
      word_count: 24,
      block_count: 4,
      char_count: 160,
      detected_language: "en",
      parser_name: "fixture",
      parser_version: "1.0.0",
      ocr_confidence: null,
    },
    warnings: [],
  },
  blocks,
  metrics: {
    similarity: 0.91,
    edit_count: 0,
    insertions: 0,
    deletions: 0,
    unchanged_tokens: 24,
    churn: 0,
    blocks_moved: 1,
    blocks_split: 1,
    blocks_merged: 1,
    a_word_count: 24,
    b_word_count: 24,
  },
  options: {
    granularity: "WORD",
    detect_moves: true,
    align_threshold: 0.5,
    move_threshold: 0.75,
    ignore_case: false,
    ignore_punctuation: false,
    normalize_whitespace: true,
  },
  truncated: false,
  total_blocks: blocks.length,
};

async function routeStructuralComparison(page: Page) {
  await page.route("https://palimpsest.test/api/v1/comparisons/structural-fixture**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(comparison),
    });
  });

  await page.route("https://palimpsest.test/c/structural-fixture**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/html",
      body: structuralPage(route.request().url()),
    });
  });
}

function structuralRows(movesEnabled: boolean): string {
  return blocks.map((block) => structuralRowPair(block, movesEnabled)).join("");
}

function markerGlyph(block: DiffBlock): string {
  if (!movesEnabledStatus(block) || block.status === "UNCHANGED") {
    return "";
  }
  if (block.status === "MOVED") {
    return "◆";
  }
  if (block.status === "SPLIT") {
    return "⑂";
  }
  if (block.status === "MERGED") {
    return "⑃";
  }
  return "";
}

function movesEnabledStatus(block: DiffBlock): boolean {
  return block.status === "MOVED" || block.status === "SPLIT" || block.status === "MERGED";
}

function connectorGlyph(block: DiffBlock): string {
  if (block.status === "SPLIT") {
    return "┬";
  }
  if (block.status === "MERGED") {
    return "┴";
  }
  if ((block.move_distance ?? 0) < 0) {
    return "↑";
  }
  if ((block.move_distance ?? 0) > 0) {
    return "↓";
  }
  return "◆";
}

function movementText(block: DiffBlock): string {
  const distance = block.move_distance ?? 0;
  if (distance === 0) {
    return "moved to a different position";
  }
  const magnitude = Math.abs(distance);
  return `moved ${magnitude} ${magnitude === 1 ? "block" : "blocks"} ${
    distance < 0 ? "earlier" : "later"
  }`;
}

function textFor(block: DiffBlock, side: "a" | "b"): string {
  const tokens = side === "a" ? block.a_tokens : block.b_tokens;
  return tokens.map((item) => item.text).join("");
}

function structuralRow(block: DiffBlock, side: "a" | "b", movesEnabled: boolean): string {
  const marker = movesEnabled || !movesEnabledStatus(block) ? markerGlyph(block) : "";
  const relationship =
    block.status === "MOVED"
      ? movementText(block)
      : `${block.status.toLowerCase()} group ${block.group_id}`;

  return `<div
      data-testid="diff-block-row-${block.id}"
      data-status="${block.status}"
      data-group-id="${block.group_id ?? ""}">
      <div data-testid="change-gutter">
        <span data-testid="gutter-marker-${block.status}">${marker}</span>
        <span>${side === "a" ? block.a_index ?? "" : block.b_index ?? ""}</span>
      </div>
      <p><span>${relationship}</span> ${textFor(block, side) || "&nbsp;"}</p>
    </div>`;
}

function structuralRowPair(block: DiffBlock, movesEnabled: boolean): string {
  const visible = movesEnabled && movesEnabledStatus(block);
  return `${structuralRow(block, "a", movesEnabled)}
    <div
      aria-hidden="true"
      data-testid="block-connector-${block.id}"
      data-status="${block.status}"
      data-visible="${visible}"
      data-group-id="${block.group_id ?? ""}">
      ${visible ? connectorGlyph(block) : ""}
    </div>
    ${structuralRow(block, "b", movesEnabled)}`;
}

function structuralPage(url: string): string {
  const movesEnabled = new URL(url).searchParams.get("moves") !== "off";

  return `<!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <title>Structural fixture</title>
      </head>
      <body>
        <main>
          <div data-testid="diff-viewer" data-view="synoptic" data-moves="${movesEnabled ? "on" : "off"}">
            <button type="button" data-testid="moves-toggle" aria-pressed="${movesEnabled}">
              Structural markers ${movesEnabled ? "on" : "off"}
            </button>
            <section aria-label="Manuscript A and Manuscript B structural fixture">
              ${structuralRows(movesEnabled)}
            </section>
          </div>
        </main>
        <script>
          void fetch("https://palimpsest.test/api/v1/comparisons/structural-fixture");
          document.querySelector('[data-testid="moves-toggle"]').addEventListener("click", () => {
            const viewer = document.querySelector('[data-testid="diff-viewer"]');
            viewer.dataset.moves = "off";
            const next = new URL(window.location.href);
            next.searchParams.set("moves", "off");
            window.history.replaceState(null, "", next);
            for (const connector of document.querySelectorAll('[data-testid^="block-connector-"]')) {
              connector.setAttribute("data-visible", "false");
              connector.textContent = "";
            }
            for (const marker of document.querySelectorAll('[data-testid="gutter-marker-MOVED"], [data-testid="gutter-marker-SPLIT"], [data-testid="gutter-marker-MERGED"]')) {
              marker.textContent = "";
            }
          });
        </script>
      </body>
    </html>`;
}

async function expectNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();

  expect(results.violations).toEqual([]);
}

test("renders structural block relationships and move suppression", async ({ page }) => {
  await routeStructuralComparison(page);

  await page.goto("https://palimpsest.test/c/structural-fixture");

  await expect(page.getByTestId("gutter-marker-MOVED").first()).toContainText("◆");
  await expect(page.getByTestId("gutter-marker-SPLIT").first()).toContainText("⑂");
  await expect(page.getByTestId("gutter-marker-MERGED").first()).toContainText("⑃");
  await expect(page.getByText("moved 2 blocks later").first()).toBeAttached();

  await expect(page.getByTestId("block-connector-moved-pair")).toHaveAttribute(
    "data-visible",
    "true",
  );
  await expect(page.locator('[data-group-id="split-bell"]')).toHaveCount(6);
  await expect(page.locator('[data-group-id="merge-scribe"]')).toHaveCount(6);

  await expectNoA11yViolations(page);

  await page.getByTestId("moves-toggle").click();
  await expect(page).toHaveURL(/moves=off/);
  await expect(page.getByTestId("block-connector-moved-pair")).toHaveAttribute(
    "data-visible",
    "false",
  );
  await expect(page.getByTestId("gutter-marker-MOVED").first()).toHaveText("");

  await page.goto("https://palimpsest.test/c/structural-fixture?moves=off");
  await expect(page.locator('[data-testid="diff-viewer"][data-moves="off"]')).toBeVisible();
  await expect(page.getByTestId("block-connector-moved-pair")).toHaveAttribute(
    "data-visible",
    "false",
  );
});
