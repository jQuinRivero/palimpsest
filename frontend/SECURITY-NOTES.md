# Dependency security notes

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
