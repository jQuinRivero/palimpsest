This document defines how palimpsest proves that parsing, normalization, alignment, rendering, and API contracts remain stable as the implementation changes.

**Status:** Draft

**Related:** [Overview](./00-overview.md) · [Ingestion and parsers](./02-ingestion-and-parsers.md) · [Normalization](./03-normalization.md) · [Diff engine](./04-diff-engine.md) · [Data schema](./05-data-schema.md) · [API reference](./06-api-reference.md) · [Session storage](./07-session-storage.md) · [Components](./10-components.md) · [Performance and scale](./11-performance-and-scale.md) · [Edge cases](./12-edge-cases.md)

## Testing philosophy

Diff correctness for prose is partly subjective. There is rarely one mathematically true collation for a revised novel, a translation, or a witness with damaged extraction. The testing strategy therefore leans on golden-corpus regression: pin known-good outputs, detect drift, and require human review when the output changes.

This does not weaken the test suite. It separates objective properties from judgement calls. Token reconstruction, schema shape, expiry semantics, and parser warnings are exact. Alignment quality over literary prose is regression-tested against reviewed examples.

## Test pyramid

### Unit — parsers

Parser unit tests use a fixture corpus of small real sources per `SourceFormat`: `TXT`, `MARKDOWN`, `DOCX`, `PDF`, and future `OCR` seams where contract stubs exist. Fixtures must include deliberately malformed sources, not only happy paths.

Every `IngestionWarning.code` named in [Edge cases](./12-edge-cases.md) must have at least one test that provokes it. Every RFC 9457 error `code` that ingestion can return must also have a focused test: `UNSUPPORTED_FORMAT`, `FILE_TOO_LARGE`, `MALFORMED_DOCUMENT`, `EMPTY_DOCUMENT`, and `OCR_REQUIRED`.

`ParserCapabilities` claims are test obligations. A parser that returns `preserves_headings=True` must prove that a heading becomes a `Block` with `kind=HEADING`. A parser that returns `preserves_page_numbers=True` must prove that `Block.page` is populated where page evidence exists. A parser that returns `is_lossy=True` must have tests showing the corresponding warning or documented lossy path.

| Parser | Required assertions |
|---|---|
| `PlainTextParser` | BOM handling, fallback decoding warning, paragraph segmentation, `preserves_headings=False`. |
| `MarkdownParser` | ATX and setext `HEADING`, `QUOTE`, `LIST_ITEM`, inline formatting stripped without prose drift. |
| `DocxParser` | Heading style mapping, localized or renamed styles, tracked changes warning, non-body text warning. |
| `PdfPlumberParser` | Page numbers, `ARTIFACT` classification, reflow, dehyphenation decisions, scanned-PDF `OCR_REQUIRED`. |
| `PyPdfParser` | Lower-fidelity page extraction, fallback behaviour, scanned-PDF `OCR_REQUIRED`. |

### Unit — normalization

Normalization is pure and deterministic, so property-based testing with Hypothesis is the natural fit.

Required properties:

```text
normalize(normalize(x)) == normalize(x)
normalize(x) == normalize(x)
```

The first property is idempotence. The second is determinism: the same bytes, parser metadata, and normalization options must produce the same `Document` content, warnings, offsets, and block boundaries.

Table-driven tests cover every hyphenation and reflow rule in [Edge cases](./12-edge-cases.md): hard hyphen, soft hyphen, em dash, en dash, page-break dehyphenation, soft line breaks, verse exemption, ligature folding, NFC normalization, invisible spaces, and homoglyph preservation. Tests must assert both the normalized text and the emitted `IngestionWarning` code when one is required.

### Unit — diff engine

Diff-engine unit tests use hand-built Manuscript A and Manuscript B `Document` values that isolate one structural fact at a time.

| Scenario | Expected `BlockStatus` |
|---|---|
| Identical block | `UNCHANGED` |
| Pure insertion | `INSERTED` |
| Pure deletion | `DELETED` |
| Token modification inside aligned blocks | `MODIFIED` |
| Clean move | `MOVED` |
| One block becoming two | `SPLIT` with shared `group_id` |
| Two blocks becoming one | `MERGED` with shared `group_id` |
| Move plus edit | `MOVED` with non-zero `BlockMetrics.edit_count` |

Tests assert exact `DiffBlock` output: `status`, `kind`, `a_index`, `b_index`, `a_block_id`, `b_block_id`, `tokens`, `a_tokens`, `b_tokens`, `metrics`, `move_distance`, and `group_id`. They also assert document-level `DiffMetrics`, including `blocks_moved`, `blocks_split`, `blocks_merged`, `a_word_count`, and `b_word_count`.

High-value invariants belong in both example tests and property tests:

```text
"".join(token.text for token in diff_block.a_tokens) == original normalized Manuscript A block text
"".join(token.text for token in diff_block.b_tokens) == original normalized Manuscript B block text
```

That reconstruction invariant is cheap, exact, and catches many subtle token-stream bugs before they reach the frontend.

The full invariant suite must match [Data schema](./05-data-schema.md) exactly:

1. **Pane reconstruction (exact).** `"".join(t.text for t in a_tokens)` reproduces Manuscript A's block text character for character; likewise `b_tokens` for Manuscript B.
2. **Unified projection (word-for-word).** `tokens` filtered of `INSERTION` agrees with `a_tokens` on the word sequence, and filtered of `DELETION` agrees with `b_tokens`. Whitespace may legitimately differ; see below.
3. `a_tokens` contains no `INSERTION`; `b_tokens` contains no `DELETION`.
4. `metrics.edit_count == metrics.insertions + metrics.deletions`, at both block and document level.
5. `a_index` is `null` if and only if `status == INSERTED`. `b_index` is `null` if and only if `status == DELETED`.
6. `move_distance` is non-null if and only if `status == MOVED`.
7. `group_id` is non-null if and only if `status` is `SPLIT` or `MERGED`, and every member of a group shares one value.
8. `blocks` is ordered for reading: by `b_index` where present, otherwise positioned at the deleted block's place in the A sequence.
9. When `truncated` is `false`, `len(blocks) == total_blocks`.

Invariant 2 is deliberately weaker than invariant 1 because the unified stream is a third rendering rather than a copy of either pane: it must insert separators so that adjacent runs cannot fuse into a single word, and under `normalize_whitespace` two runs can compare equal while carrying different trailing whitespace. Tests must assert the word sequence here, not the byte sequence. Two regressions this specifically guards against, both found during implementation, are `"four five"` + `"six"` rendering as `four fivesix`, and a deletion immediately followed by an insertion rendering as `alphabeta`.

A property test over a small fixed vocabulary is the most effective form: generate two word sequences, diff them, and assert that every word in the unified stream is a member of the vocabulary. Any fusion produces a word that is not.

These checks belong in a single shared helper asserted by every engine, formatting, and API test, so that the specification's own payload examples and the running engine are judged by identical code.

### Golden corpus

The golden corpus contains real public-domain witness pairs with committed expected `ComparisonResult` payloads. Plausible seed pairs include different public-domain editions of a nineteenth-century novel, such as two early editions of *Frankenstein*, a serial and book edition of a public-domain novel, and an original public-domain translation compared against a later revised public-domain translation.

Golden tests pin the whole reviewed payload, not only metrics. A change to block alignment, token cleanup, `BlockStatus`, or warning emission must produce a visible diff in the golden output.

When a diff genuinely improves, the golden file may be updated only through a documented review procedure:

1. Generate the new `ComparisonResult` from unchanged source fixtures.
2. Inspect structural changes in both synoptic and unified view.
3. Record why the new output is more faithful to the witnesses.
4. Commit the source fixture, expected payload, and review note together.

Golden files must never be updated merely to silence CI.

### Contract tests

Contract drift is a release blocker.

The generated OpenAPI schema at `/api/v1/openapi.json` is compared against [API reference](./06-api-reference.md), including endpoint paths, status codes, request bodies, response bodies, and RFC 9457 error shape. The comparison must verify the exact paths `/api/v1/documents`, `/api/v1/comparisons`, `/api/v1/comparisons/{comparison_id}`, `/api/v1/comparisons/{comparison_id}/blocks`, `/api/v1/capabilities`, and `/api/v1/health`.

TypeScript types are generated from the OpenAPI schema in CI and committed as generated artifacts. They are not hand-maintained. The point is that TypeScript types cannot drift from Pydantic models in `backend/app/models/{document,diff,api}.py`; drift is made impossible rather than merely discouraged.

### API and integration tests

FastAPI `TestClient` covers the full lifecycle:

```text
POST /api/v1/documents
POST /api/v1/documents
POST /api/v1/comparisons
GET /api/v1/comparisons/{comparison_id}
GET /api/v1/comparisons/{comparison_id}/blocks
DELETE /api/v1/comparisons/{comparison_id}
DELETE /api/v1/documents/{document_id}
```

Integration tests assert every contract error code: `UNSUPPORTED_FORMAT`, `FILE_TOO_LARGE`, `MALFORMED_DOCUMENT`, `EMPTY_DOCUMENT`, `DOCUMENT_NOT_FOUND`, `COMPARISON_NOT_FOUND`, `COMPARISON_EXPIRED`, `DIFF_BUDGET_EXCEEDED`, `OCR_REQUIRED`, `RATE_LIMITED`, and `INTERNAL_ERROR` where controlled fault injection is available.

The `202` accepted path is mandatory. A test must force the asynchronous comparison path, assert `ComparisonAccepted`, poll `GET /api/v1/comparisons/{comparison_id}`, and receive the final `ComparisonResult` without changing `comparison_id`.

### Storage tests

Storage tests exercise the `SessionStore` contract and the SQLite implementation.

| Area | Required assertions |
|---|---|
| TTL expiry | Reads check `expires_at` before returning content. |
| Sweeper | Expired rows are deleted without touching live rows. |
| Stale comparison | Expired comparisons return `COMPARISON_EXPIRED` before payload disclosure. |
| Cascade behaviour | Deleting an expired document removes dependent comparisons, and stale reads become `COMPARISON_EXPIRED`. |
| WAL concurrency | Many readers can proceed while writes serialize under `journal_mode=WAL`, `busy_timeout=5000`, and `foreign_keys=ON`. |
| Serialization | `blocks_json`, `metadata_json`, `warnings_json`, `options_json`, and `metrics_json` round-trip exactly. |

### Frontend tests

Component tests cover every component named in [Components](./10-components.md): `ManuscriptUploader`, `DiffViewer`, `VirtualizedSynopticView`, `VirtualizedUnifiedView`, `DiffSummaryBar`, `DiffBlockRow`, `TokenSpan`, `ChangeGutter`, `ChangeNavigator`, `LoadingProgress`, `BlockConnector`, and `EmptyState`.

Tests must exercise the real components. A fixture that serves hand-written HTML and reimplements the behaviour under test asserts only that the test file is self-consistent, and will pass with the component broken or deleted. Where a route fetches server-side and cannot be intercepted from the browser, drive the real API rather than substituting a facsimile of the page. A structural-rendering fixture doing exactly this was removed for that reason.

The corresponding check is mutation, not coverage: change a rendered glyph or label and confirm the test fails. Coverage cannot distinguish a test that exercises a component from one that merely renders beside it.

Both reading views get special attention, because virtualization breaks the assumption that everything in the payload is in the DOM. Tests should cover a jump to a block that has never been mounted, `MOVED`, `SPLIT`, and `MERGED` relationships, unequal cell heights within a row, and the single-column collapse below the `md` breakpoint.

Virtualization tests use a large `ComparisonResult` payload and assert that visible rows render, offscreen rows do not explode DOM size, anchor jumps remain stable, and accessible names remain present when rows mount and unmount.

Two assertions belong together and must be made against a manuscript longer than the mounted-row budget, because each is the other's failure mode: on screen the mounted rows stay bounded, and under emulated print media every block is present. Testing only the first invites a view that never prints the whole text; testing only the second invites a view that mounts the whole manuscript.

Windowing is tested end to end against a lowered `PALIMPSEST_COMPARISON_WINDOW_BLOCK_THRESHOLD`, so a few hundred blocks exercise the path production reaches at a few thousand. This is the same technique as testing pagination with a page size of two: what is under test is the client's response to `truncated: true`, which does not depend on the absolute size. The first attempt used a genuinely oversized comparison and made the whole suite flaky, because seconds of CPU-bound diffing in the API process starved every test running beside it, failing a different unrelated test on each run.

Two rules follow. The harness must assert that the fixture really was windowed, or a raised threshold would leave the tests passing while exercising nothing. And any environment that starts the API for end-to-end runs must set the same values — Playwright's `webServer` and CI's start step both do, and they have to agree.

### End-to-end

Playwright covers the researcher journey:

1. Upload Manuscript A and Manuscript B on `/`.
2. Receive or poll for a comparison.
3. Read the comparison at `/c/[comparisonId]`.
4. Switch between `?view=synoptic` and `?view=unified`.
5. Deep-link to `?view=unified&block=<index>` and verify focus lands on the intended `DiffBlockRow`.
6. Toggle `?moves=off` and verify move-specific rendering changes without losing token diffs.

End-to-end tests use small public-domain fixtures so they remain fast enough to run with ordinary PR validation.

### Accessibility tests

Automated axe checks run against upload, synoptic view, unified view, empty states, and error states. Automated checks are necessary but not sufficient.

Manual accessibility checks follow [Design system](./09-design-system.md):

| Requirement | Manual check |
|---|---|
| Screen-reader announcement | `INSERTION`, `DELETION`, `MOVED`, `SPLIT`, and `MERGED` are announced with block context. |
| Keyboard navigation | A researcher can move between changes and return focus to the manuscript text without a mouse. |
| Non-colour encoding | Insertions, deletions, moves, splits, and merges remain distinguishable without colour. |
| Synoptic and unified modes | Reading order is coherent in both modes and with RTL text. |
| Reduced motion | Connectors and scroll jumps do not require animation to understand state. |

### Performance regression

The standing benchmark corpus asserts the budgets defined in [Performance and scale](./11-performance-and-scale.md). Benchmarks cover parser throughput, normalization, block alignment, token diffing, payload size, API response time, frontend rendering, and virtualization.

CI uses a tolerance band rather than a single brittle number. Regressions outside the band fail and require either a fix or a documented budget change in [Performance and scale](./11-performance-and-scale.md).

## Fixtures

Fixtures live under a test corpus root with format-specific and purpose-specific subdirectories:

```text
tests/fixtures/
  ingestion/
    txt/
    markdown/
    docx/
    pdf/
  normalization/
    hyphenation/
    unicode/
    reflow/
  diff/
    block-status/
    pathologies/
  golden/
    sources/
    expected/
    reviews/
```

Committed manuscripts must be public domain or project-authored. This matters because the repository is Apache-2.0 and public: test fixtures are redistributed with the source. Do not commit copyrighted modern editions, licensed scans, or user uploads.

Keep the committed corpus small enough that cloning the repository remains reasonable. Large performance fixtures should be generated deterministically, stored through release artifacts, or fetched only by opt-in benchmark jobs when licensing permits.

Each fixture includes a manifest recording source, license status, parser target, expected warnings, and whether it is allowed in ordinary CI.

## CI

Every PR runs the checks that protect correctness and contract shape:

- Python linting with ruff.
- Python typing with mypy.
- Backend unit tests for parsers, normalization, diffing, API, and storage.
- Frontend linting with eslint.
- Frontend type checking with tsc.
- Component tests for the diff viewer surface.
- Contract generation and OpenAPI-to-TypeScript type generation.
- A small golden-corpus subset.
- Playwright smoke coverage for upload and comparison rendering.

Nightly CI runs the heavier checks:

- Full golden corpus.
- Full Playwright journey matrix.
- Accessibility pass including axe and manual-check prompts.
- Performance regression corpus with tolerance bands.
- Storage concurrency stress tests.

Coverage expectations are a floor, not a goal. Backend and frontend line coverage must not fall below the configured threshold, but percentage is a weak signal for this system: one shallow test can cover a parser branch without proving the extracted prose is faithful, while one golden test can protect a large amount of meaningful behaviour. Reviewers should value invariant, contract, and corpus coverage over raw percentage.
