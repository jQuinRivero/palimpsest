# ADR-0001 — Use the community diff-match-patch fork

**Status:** Accepted
**Related:** [Diff engine](../04-diff-engine.md) · [Performance and scale](../11-performance-and-scale.md) · [Testing strategy](../13-testing-strategy.md)

## Context

`palimpsest` needs a proven token diff library. Writing a custom diff algorithm is explicitly out of scope, but the obvious default, Google's `google/diff-match-patch`, is archived and its GitHub repository was last pushed on 2024-05-22. The chosen library must support the server-side word-level prose diff described by the diff engine, remain compatible with Python 3.12+, and fit the project's Apache-2.0 license.

## Options considered

- The community `diff-match-patch` fork under the `diff-match-patch-python` organisation. It now holds the PyPI name, is available as version `20241021`, is Apache-2.0, is pure Python, and is actively maintained. Its major advantage is API continuity with the original library, including the `diff_linesToChars` and `diff_charsToLines` line-mode helpers.
- `fast-diff-match-patch` `2.1.0`. It is Apache-2.0, uses a C++ binding, releases the GIL, and is roughly 10–100× faster on large documents. That is genuinely attractive for 100k-word witnesses where server CPU is a real cost.
- `difflib.SequenceMatcher` from the standard library. It has no dependency, no license friction, and is easy to understand. It is also slower and less purpose-built for producing the token streams the renderer needs.
- Writing our own diff algorithm. This would give complete control over prose-specific behaviour, but it would spend the project on an algorithmic problem already solved elsewhere and would be difficult to validate against mature implementations.

## Decision

Use the community `diff-match-patch` fork, version `20241021`, for word-level diffing.

The deciding factor is the `diff_linesToChars` and `diff_charsToLines` line-mode helper pair. `palimpsest` remaps word sequences into a character alphabet before diffing and then maps the result back to tokens. `fast-diff-match-patch` exposes only a simplified `diff()` API and omits those helpers, so its speed advantage is unusable for the required algorithm. It also lacks current Python 3.13 and 3.14 wheels, with its last release in 2021. The community fork preserves the needed API and its Apache-2.0 license matches the project exactly.

## Consequences

The cost is that pure-Python word diffing is slower than the C++ binding. That cost is acceptable only because the alignment stage reduces the amount of text sent into word-level diffing, and because [Performance and scale](../11-performance-and-scale.md) defines budgets, payload windowing, and a degradation ladder up to `DIFF_BUDGET_EXCEEDED`. `difflib.SequenceMatcher` remains a reasonable fallback and is useful in tests as an independent oracle, but it is not the production engine.

Revisit this decision if `fast-diff-match-patch` gains the line-mode helpers and current Python wheels, or if profiling shows that word diffing, rather than block alignment, dominates real workloads.
