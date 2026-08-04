/**
 * Regenerate `lib/api-types.ts` from the backend's OpenAPI schema.
 *
 * The generated file is committed so schema changes are visible in review, and
 * CI runs this with `--check` to fail on drift. Types are never hand-edited:
 * a hand-maintained mirror of a backend schema drifts silently, and a drift
 * here is a rendering bug rather than a loud failure.
 *
 *   node scripts/generate-api-types.mjs           # write
 *   node scripts/generate-api-types.mjs --check   # fail if out of date
 *
 * Requires the backend to be running:
 *   cd backend && uv run uvicorn app.main:app --port 8000
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync, rmSync, mkdtempSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { dirname, resolve, join } from "node:path";
import { tmpdir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const output = resolve(here, "..", "lib", "api-types.ts");
const schemaUrl =
  process.env.PALIMPSEST_API_URL ?? "http://127.0.0.1:8000/api/v1/openapi.json";
const check = process.argv.includes("--check");

// Resolve the CLI's JS entry point and run it with node directly. Node 24
// refuses to spawn .cmd shims (EINVAL), and going through a shell would mean
// quoting a URL on the command line.
const require = createRequire(import.meta.url);
const cli = resolve(
  dirname(require.resolve("openapi-typescript/package.json")),
  "bin",
  "cli.js",
);

// openapi-typescript prints a progress banner to stdout, so capturing stdout
// would corrupt the generated module. Write to a temp file and read that back.
const scratch = mkdtempSync(join(tmpdir(), "palimpsest-types-"));
const scratchFile = join(scratch, "api-types.ts");
let generated;

try {
  execFileSync(process.execPath, [cli, schemaUrl, "-o", scratchFile], {
    stdio: ["ignore", "ignore", "inherit"],
  });
  generated = readFileSync(scratchFile, "utf8");
} catch (error) {
  console.error(
    `\nCould not read the OpenAPI schema from ${schemaUrl}.\n` +
      `  ${error.message}\n` +
      "Start the backend first:\n" +
      "  cd backend && uv run uvicorn app.main:app --port 8000\n",
  );
  process.exit(1);
} finally {
  rmSync(scratch, { recursive: true, force: true });
}

const normalise = (text) => text.replace(/\r\n/g, "\n").trim();

if (check) {
  if (!existsSync(output)) {
    console.error("lib/api-types.ts is missing. Run without --check.");
    process.exit(1);
  }
  if (normalise(readFileSync(output, "utf8")) !== normalise(generated)) {
    console.error(
      "\nlib/api-types.ts is out of date with the backend schema.\n" +
        "Run: node scripts/generate-api-types.mjs\n",
    );
    process.exit(1);
  }
  console.log("api-types.ts matches the backend schema.");
} else {
  writeFileSync(output, generated, "utf8");
  console.log(`Wrote ${output}`);
}
