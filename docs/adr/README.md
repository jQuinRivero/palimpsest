# Architecture decision records

Records of the contested calls — the ones where a reasonable engineer could have gone the other way, and where knowing *why* matters more than knowing *what*. Uncontested choices are documented in the specification proper, not here.

**Status:** Draft

**Related:** [Documentation index](../README.md)

Format adapted from Michael Nygard's original ADR pattern.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](./0001-diff-match-patch-fork.md) | Use the community `diff-match-patch` fork, not Google's archived upstream or the C++ binding | Accepted |
| [0002](./0002-pdfplumber-over-pymupdf.md) | Use `pdfplumber` for PDF extraction; reject `PyMuPDF` on license grounds | Accepted |
| [0003](./0003-sqlite-session-store.md) | Cache sessions in SQLite with a TTL rather than in process memory | Accepted |
| [0004](./0004-server-side-diff-computation.md) | Compute diffs on the server and ship a finished payload to the client | Accepted |
| [0005](./0005-tailwind-v4-css-first-tokens.md) | Adopt Tailwind v4 CSS-first `@theme` tokens; no `tailwind.config.js` | Accepted |
| [0006](./0006-tei-parallel-segmentation-export.md) | Export TEI P5 using parallel segmentation; encode structural relations as `<linkGrp>` | Accepted |
| [0007](./0007-stanza-boundaries.md) | Carry stanza boundaries through verse segmentation rather than losing them | Accepted |
| [0008](./0008-weak-copyleft-dependency-review.md) | Allow current weak-copyleft dependencies with review | Accepted |

## Conventions

Records are numbered sequentially and never renumbered. A record is immutable once accepted: to change a decision, write a new record that supersedes it and update the older record's status to `Superseded by ADR-NNNN`. Status is one of `Proposed`, `Accepted`, `Superseded`, or `Deprecated`.

## Template

```markdown
# ADR-NNNN — <short imperative title>

**Status:** Proposed | Accepted | Superseded by ADR-NNNN | Deprecated
**Related:** links to affected specification documents

## Context

The forces at play: what constraint, requirement, or discovery made this a decision
rather than a default. State the licensing position if a dependency is involved.

## Options considered

Each option with its genuine merits, not a straw man.

## Decision

What we are doing, stated plainly.

## Consequences

What this buys us, what it costs us, and what it forecloses. Include the conditions
under which this decision should be revisited.
```
