# Architecture decisions

The full ADRs live under `docs/adr/`. This page surfaces the accepted decisions without copying their text.

| ADR | Summary | Link |
|---|---|---|
| ADR-0001 | Use the maintained Python `diff-match-patch` fork because palimpsest needs the line-mode helpers for word-level remapping and an Apache-2.0-compatible dependency. | [Full ADR](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0001-diff-match-patch-fork.md) |
| ADR-0002 | Use `pdfplumber` by default and `pypdf` as a lower-fidelity path; do not use AGPL `PyMuPDF` in an Apache-2.0 project. | [Full ADR](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0002-pdfplumber-over-pymupdf.md) |
| ADR-0003 | Store documents and comparisons in SQLite with TTL because sessions must outlive a request but are a cache, not an archive. | [Full ADR](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0003-sqlite-session-store.md) |
| ADR-0004 | Compute diffs on the server and return a structured payload so the algorithm, budgets, and contract stay centralized. | [Full ADR](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0004-server-side-diff-computation.md) |
| ADR-0005 | Use Tailwind v4 CSS-first `@theme` tokens instead of a default `tailwind.config.js`, keeping manuscript design tokens as CSS variables. | [Full ADR](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0005-tailwind-v4-css-first-tokens.md) |
| ADR-0006 | Export TEI P5 using parallel segmentation and encode moves, splits, and merges as TEI links in back matter. | [Full ADR](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0006-tei-parallel-segmentation-export.md) |
| ADR-0007 | Preserve stanza boundaries during verse segmentation so redividing a poem is reported as structural change. | [Full ADR](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0007-stanza-boundaries.md) |
| ADR-0008 | Allow the current unmodified MPL-2.0 dependencies, keep reporting them for review, and require a new decision if their role or modification status changes. | [Full ADR](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0008-weak-copyleft-dependency-review.md) |

ADR index: [docs/adr/README.md](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/README.md).
