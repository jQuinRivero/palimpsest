# Dependency security notes

## `npm ci` requires npm 11.6.x

`package-lock.json` installs cleanly under npm **11.6.2** and is rejected by
npm **11.8 and newer**:

```
npm error code EUSAGE
npm error Missing: @emnapi/core@ from lock file
npm error Missing: @emnapi/runtime@ from lock file
npm error Missing: @napi-rs/wasm-runtime@ from lock file
```

Those three are optional peers of `@unrs/resolver-binding-wasm32-wasi`, a
WebAssembly fallback that no supported platform installs. Under 11.6.2 npm
reports the same conflict as an `ERESOLVE` **warning** and proceeds; from 11.8
it treats it as a lockfile inconsistency and refuses.

Regenerating with a newer npm does not resolve it. `npm install
--package-lock-only` under 11.16 *removes* those entries — changing no package
version, only pruning five optional records — after which `npm ci` under the
same npm reports them as missing again. `npm install` and `npm ci` disagree
with each other, so this is an npm defect rather than a stale lockfile.

**Impact.** Anyone cloning with a current Node release cannot install the
frontend. CI is unaffected only because `actions/setup-node` currently supplies
npm 11.6.2 with Node 24.18.0 — when that moves, CI breaks with no change to
this repository. `frontend/Dockerfile` therefore pins npm to 11.6.2 explicitly
rather than inheriting whichever npm its base image was rebuilt with.

**Action:** re-test on each npm release. The fix is upstream; when a version
accepts the lockfile, drop the pin in `frontend/Dockerfile` and record the
minimum here. Do not "fix" this by re-resolving the dependency graph — the
overrides above are deliberate and no package version is actually wrong.

## `npm audit` residual: 5 high advisories

`npm audit` reports 5 high-severity advisories in the frontend. All five are the
same root cause cascading through the dependency graph:

```
brace-expansion  →  minimatch  →  @eslint/config-array
                                  @eslint/eslintrc      →  eslint
```

**There is currently no fixed version of `brace-expansion` published.** Every
release line is covered by an overlapping advisory:

| Line | Latest published | Advisory |
|---|---|---|
| 1.x | 1.1.16 | GHSA-mh99-v99m-4gvg — affects `<=1.1.16` |
| 2.x | 2.1.3 | GHSA-rgw5-rvv9-x895 — affects `>=2.0.0 <2.1.4` |
| 3.x–5.x | 5.0.8 | GHSA-3jxr-9vmj-r5cp and GHSA-rgw5 — affect `3.0.0 - 5.0.6` and `>=4.0.0` |

We pin `brace-expansion` to `2.1.3` because it is the least-exposed option: it
clears GHSA-mh99 and GHSA-3jxr, reducing the reported total from 18 to 5. The
remaining GHSA-rgw5 has no published fix at the time of writing.

**Assessed risk: low.** The advisories are denial-of-service via pathological
glob patterns, the package is reachable only from ESLint's config-file matching,
and it is a `devDependency` that is never bundled into the browser build. An
attacker would need to control the contents of our lint configuration, at which
point they already have code execution in CI.

**Action:** re-run `npm audit` when `brace-expansion >= 2.1.4` or a patched
`>= 5.0.9` is published, then drop or raise the override.

## Overrides that fixed real issues

| Package | Pinned | Why |
|---|---|---|
| `postcss` | `^8.5.24` | Clears XSS via unescaped `</style>`, and path traversal / arbitrary file read via attacker-controlled `sourceMappingURL` (GHSA-qx2v, GHSA-6g55, GHSA-r28c) |
| `sharp` | `^0.35.3` | Clears inherited libvips CVEs (GHSA-f88m-g3jw-g9cj). `sharp` is an *optional* Next.js dependency used only for `next/image` optimisation, which palimpsest does not use |
| `js-yaml` | `^4.3.0` | Clears quadratic CPU consumption via YAML merge-key chains. Reached through `openapi-typescript`'s Redocly parser, which reads the backend's OpenAPI schema |

## Next.js version

The specification names Next.js `16.3.0`. Only pre-release builds of `16.3.0`
are published (`16.3.0-preview.9` is the current `latest` dist-tag). We pin the
highest **stable** release, `16.2.12`, rather than ship a preview build as the
foundation of the project.

`npm audit` flags `next` up to `16.3.0-preview.7`; that advisory is the bundled
`sharp` issue, which our `sharp` override resolves independently without moving
to a pre-release.

Revisit when `16.3.0` reaches stable.
