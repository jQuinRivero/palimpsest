// Start, wait for, and stop the development servers, and seed a comparison.
//
// Shared by capture_screenshots.mjs and capture_demo.mjs. Both need the same
// pair of servers and the same seeded comparison, and a second copy of the
// Windows process-tree teardown below is exactly the kind of thing that rots
// in one file and not the other.
import { spawn } from "node:child_process";
import { once } from "node:events";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

const here = dirname(fileURLToPath(import.meta.url));
export const repo = resolve(here, "..");

export const apiPort = process.env.PALIMPSEST_DOCS_API_PORT ?? "8000";
export const webPort = process.env.PALIMPSEST_DOCS_WEB_PORT ?? "3000";
export const apiBase = `http://127.0.0.1:${apiPort}`;
export const webBase = `http://127.0.0.1:${webPort}`;

// One passage moves, one splits, and exactly one word changes. Small enough to
// read at a glance and still exercise every kind of change the tool reports.
export const witnessA = `It was the best of times, it was the worst of times.

It was the age of wisdom, it was the age of foolishness.

We had everything before us. We had nothing before us.`;

export const witnessB = `It was the age of wisdom, it was the age of foolishness.

It was the best of times, it was the worst of times.

We had everything before us.

We had little before us.`;

export function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function ok(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(2000) });
    return response.ok;
  } catch {
    return false;
  }
}

export async function waitFor(url, label) {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    if (await ok(url)) return;
    await sleep(1000);
  }
  throw new Error(`${label} did not become ready at ${url}`);
}

function spawnLogged(command, args, options) {
  const child = spawn(command, args, {
    cwd: options.cwd ?? repo,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    ...options,
  });
  child.stdout.on("data", (chunk) => process.stdout.write(`[${options.name}] ${chunk}`));
  child.stderr.on("data", (chunk) => process.stderr.write(`[${options.name}] ${chunk}`));
  return child;
}

export async function startApi() {
  if (await ok(`${apiBase}/api/v1/health`)) return null;

  const venvPython =
    process.platform === "win32"
      ? resolve(repo, "backend", ".venv", "Scripts", "python.exe")
      : resolve(repo, "backend", ".venv", "bin", "python");
  const child = existsSync(venvPython)
    ? spawnLogged(
        venvPython,
        ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", apiPort],
        { name: "api", cwd: resolve(repo, "backend") },
      )
    : spawnLogged(
        "uv",
        [
          "--directory",
          "backend",
          "run",
          "uvicorn",
          "app.main:app",
          "--host",
          "127.0.0.1",
          "--port",
          apiPort,
        ],
        { name: "api" },
      );
  await waitFor(`${apiBase}/api/v1/health`, "API");
  return child;
}

export async function startWeb() {
  if (await ok(webBase)) return null;
  const next = resolve(repo, "frontend", "node_modules", "next", "dist", "bin", "next");
  const child = spawnLogged(
    process.execPath,
    [next, "dev", "--hostname", "127.0.0.1", "--port", webPort],
    {
      name: "web",
      cwd: resolve(repo, "frontend"),
      env: { ...process.env, NEXT_PUBLIC_API_URL: apiBase },
    },
  );
  await waitFor(webBase, "web server");
  return child;
}

export async function stopChild(child) {
  if (!child || child.exitCode !== null) return;

  if (process.platform === "win32") {
    // uv's Windows virtual-environment launcher starts the real interpreter as
    // a child. Killing only the launcher leaves uvicorn listening forever, so
    // terminate the exact descendant tree rooted at the PID we started. This
    // never matches by process name and cannot touch an unrelated server.
    const script = `
function Stop-Tree([int]$ProcessId) {
  @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue) |
    ForEach-Object { Stop-Tree ([int]$_.ProcessId) }
  Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}
Stop-Tree ${child.pid}
`;
    const stopper = spawn(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      { stdio: "ignore", windowsHide: true },
    );
    await once(stopper, "exit");
    return;
  }

  child.kill();
  await Promise.race([once(child, "exit"), sleep(5000)]);
  if (child.exitCode === null) {
    child.kill("SIGKILL");
    await Promise.race([once(child, "exit"), sleep(5000)]);
  }
}

async function uploadText(title, text) {
  const form = new FormData();
  form.append("title", title);
  form.append("file", new Blob([text], { type: "text/plain" }), `${title}.txt`);
  const response = await fetch(`${apiBase}/api/v1/documents`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function createComparison() {
  const a = await uploadText("Manuscript A", witnessA);
  const b = await uploadText("Manuscript B", witnessB);
  const response = await fetch(`${apiBase}/api/v1/comparisons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ a_document_id: a.id, b_document_id: b.id }),
  });
  if (!response.ok) throw new Error(await response.text());
  const comparison = await response.json();
  console.log(
    JSON.stringify({
      comparison_id: comparison.comparison_id,
      blocks_moved: comparison.metrics.blocks_moved,
      blocks_split: comparison.metrics.blocks_split,
      edit_count: comparison.metrics.edit_count,
    }),
  );
  return comparison.comparison_id;
}

// The diff viewer streams and hydrates, so a screenshot taken on load catches
// a skeleton. Every capture has to wait for this.
export async function waitForViewer(page) {
  await page.getByTestId("diff-viewer").waitFor({ state: "visible" });
  await page.waitForFunction(
    () =>
      document.querySelector('[data-testid="diff-viewer"]')?.getAttribute("data-hydrated") ===
      "true",
  );
}
