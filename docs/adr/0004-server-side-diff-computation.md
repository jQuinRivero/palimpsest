# ADR-0004 — Compute diffs on the server

**Status:** Accepted
**Related:** [Architecture](../01-architecture.md) · [Diff engine](../04-diff-engine.md) · [API reference](../06-api-reference.md) · [Frontend architecture](../08-frontend-architecture.md) · [Performance and scale](../11-performance-and-scale.md)

## Context

The diff could plausibly run in the browser. The witness text is already involved in the interaction, a browser diff would eliminate a round trip, and option changes could be reflected immediately. That is an attractive model for a highly interactive reader.

`palimpsest`, however, is not a simple line diff. The engine aligns blocks with `rapidfuzz`, detects moved, split, and merged passages, and then performs word-level `diff-match-patch` diffing within aligned pairs. Parsing `.docx` and `.pdf` also has to happen server-side, so the canonical text is already present on the backend before collation begins.

## Options considered

- Client-side diffing in JavaScript. It gives instant re-diffing for option changes, reduces server CPU, and can feel more responsive for small witnesses. Its weaknesses are duplicate implementation, weak library support, and poor worst-case behaviour on a researcher's machine.
- Server-side diffing with a structured payload. It centralises the algorithm in Python, lets the backend enforce budgets, and creates a stable API artifact that other digital-humanities tools can consume.
- A hybrid model where the server aligns blocks and the client diffs within blocks. This reduces some server CPU and keeps expensive alignment off the laptop, but it still splits the algorithm across languages and creates two places for tokenisation and options semantics to drift.

## Decision

Compute diffs on the server and return a finished structured payload to the client.

The two-stage engine is substantial logic that would otherwise need to exist twice, in Python and JavaScript, and stay in agreement. That divergence risk is not acceptable for a scholarly reading tool. Aligning 2,000×2,000 blocks on a researcher's laptop can hang the tab, while the server can apply budgets, return `202` for accepted work, and stop with `DIFF_BUDGET_EXCEEDED` when necessary. A single implementation is also testable against the golden corpus in [Testing strategy](../13-testing-strategy.md). The npm `diff-match-patch` package has been frozen at `1.0.5` since 2018, so the client-side option is not well-supported.

The payload is the API, not an internal rendering detail. Returning `ComparisonResult`, `DiffBlock`, `Token`, and metrics as documented data makes the result usable beyond the first-party Next.js client.

## Consequences

Every option change that affects collation requires a round trip. The response payload can be larger than the source text, so [Performance and scale](../11-performance-and-scale.md) specifies block pagination, windowing, and truncation behaviour. Server CPU becomes a product concern, which forces the `202` accepted path and the `DIFF_BUDGET_EXCEEDED` ceiling.

The client becomes a pure renderer, which is a real simplification: it handles view mode, scrolling, typography, and interaction rather than algorithmic truth. Revisit this decision if interactive option-tweaking becomes a core workflow, or if a mature JavaScript stack emerges that can share the same algorithm and golden-corpus expectations without drift.
