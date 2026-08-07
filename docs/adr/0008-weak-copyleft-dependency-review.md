# ADR-0008 — Allow current weak-copyleft dependencies with review

**Status:** Accepted
**Related:** [ADR-0002](./0002-pdfplumber-over-pymupdf.md) · [Third-party notices](../../THIRD-PARTY-NOTICES.md)

## Context

ADR-0002 rejects strong copyleft for an Apache-2.0 distribution, and
`backend/scripts/check_licences.py` enforces that rule across installed Python
and npm dependencies.

The installed trees also contain weak/file-level copyleft. The Python audit has
reported `certifi`, `hypothesis`, and `pathspec` as MPL-2.0 review items, but
the conclusion was only implicit. Extending the audit to npm adds the same class
of review item for `@axe-core/playwright`, `axe-core`, `lightningcss`, and the
installed platform package `lightningcss-win32-x64-msvc`.

MPL-2.0 is not the same licensing problem as GPL, AGPL, or SSPL. It attaches to
the MPL-licensed files and requires modifications to those files to remain
available under MPL-2.0. It does not relicense a larger work that merely depends
on unmodified MPL files.

## Options considered

- **Ban every copyleft token.** Simple to automate, but too blunt: it would
  reject file-level copyleft that does not infect this Apache-2.0 application and
  would remove useful tooling for no corresponding distribution benefit.
- **Allow weak copyleft silently.** Legally plausible for unmodified MPL files,
  but inconsistent with ADR-0002's rule that dependency licence choices are
  recorded rather than assumed.
- **Allow the current weak-copyleft packages and keep reporting them for review.**
  This distinguishes Apache-compatible file-level obligations from strong
  copyleft while preserving an explicit checkpoint for future dependency changes.

## Decision

Allow the current weak-copyleft dependencies.

`certifi` is an MPL-2.0 CA certificate bundle consumed unmodified. `hypothesis`
is a test-only Python dependency and is not distributed with the application.
`pathspec` is pulled in by development tooling and is not an application runtime
dependency.

The npm MPL-2.0 packages are also acceptable. `@axe-core/playwright` and
`axe-core` are accessibility-test tooling. `lightningcss` and its installed
Windows native package are build-time CSS tooling pulled through the frontend
toolchain. In all cases, the project depends on unmodified package files rather
than incorporating modified MPL source into `palimpsest`.

`backend/scripts/check_licences.py` must keep printing MPL-2.0 and LGPL items as
`REVIEW`. A new runtime weak-copyleft dependency, or any modification to a
weak-copyleft package file, needs a new recorded decision.

## Consequences

The Apache-2.0 release remains viable: no current dependency is strong copyleft,
and the weak-copyleft packages do not impose their licence on the combined
application.

The cost is that the licence audit is intentionally not silent. Known MPL-2.0
packages continue to appear in `REVIEW` so that a future maintainer notices
when the set changes instead of treating weak copyleft as ordinary permissive
metadata.

Revisit this decision if one of these packages becomes a runtime-distributed
component with modified MPL files, if an LGPL package enters the runtime path,
or if the frontend build starts embedding MPL source text rather than generated
CSS output.
