This document sets the performance, payload, storage, and degradation budgets for comparing large witnesses without freezing the browser or exhausting the backend.

**Status:** Draft

**Related:** [README](./README.md) · [Diff engine](./04-diff-engine.md) · [API reference](./06-api-reference.md) · [Session storage](./07-session-storage.md) · [Components](./10-components.md) · [Testing strategy](./13-testing-strategy.md)

The system is allowed to degrade in documented ways. It is not allowed to silently return a worse answer or let a request die at a proxy timeout.

## Reference workload

The reference workload is a pair of prose witnesses where each witness is a 100,000-word manuscript.

| Quantity | Budget basis | Arithmetic |
|---|---:|---:|
| Words per witness | 100,000 words | Fixed reference size. |
| Source text bytes per witness | About 600 KB | 100,000 words × about 6 bytes per word including punctuation and whitespace = 600,000 bytes. |
| Blocks per witness | About 1,500-2,500 blocks | 100,000 words ÷ 40-65 words per block ≈ 1,538-2,500 blocks. |
| Tokens per witness | About 100,000 word tokens | In `WORD` granularity, one token is a word plus its trailing whitespace; punctuation remains inside the word token rather than becoming a separate token. |
| Token spans without virtualization | At least 200,000 token spans for the two synoptic panes, plus 100,000-200,000 unified-stream spans | `a_tokens` and `b_tokens` reproduce 100,000 tokens each; unified `tokens` ranges from about 100,000 tokens for unchanged witnesses to about 200,000 when most words are deleted and inserted. |

All budgets below are traceable to that workload. Larger inputs move down the degradation ladder.

## Budget table

| Stage | Target | Hard ceiling | Mitigation on breach |
|---|---:|---:|---|
| Parse | 1,500 ms per witness | 5,000 ms per witness | Return `202 ComparisonAccepted` for asynchronous comparison if both witnesses are parseable; return a problem response if parsing fails with `MALFORMED_DOCUMENT`, `EMPTY_DOCUMENT`, `UNSUPPORTED_FORMAT`, or `OCR_REQUIRED`. |
| Normalize | 500 ms per witness | 1,500 ms per witness | Disable nonessential cleanup passes that do not affect `Block` boundaries; keep `normalize_whitespace` semantics intact. |
| Tokenize | 400 ms per witness | 1,200 ms per witness | Use generator-based tokenization and skip `CHARACTER` granularity unless explicitly requested and still under budget. |
| Align | 2,000 ms | 8,000 ms | Anchor exact-match block hashes, align only gaps between anchors, apply length-ratio prefilters, score survivors with `rapidfuzz.process.extract(score_cutoff=...)`, use greedy assignment, then run LIS move detection; disable move detection before refusing. |
| Word-diff | 2,000 ms | 8,000 ms | Disable `CHARACTER` granularity first, then fall back to block-level-only changed regions for oversize aligned pairs. |
| Serialize | 600 ms | 2,000 ms | Return a truncated `ComparisonResult` with `truncated: true` and require block windowing. |
| Transfer | 1,500 ms on broadband | 5,000 ms | Use gzip or brotli; switch to windowed blocks above the payload threshold. |
| First render | 1,000 ms after payload | 2,500 ms | Render summary and the first virtual window only; defer connectors and offscreen changed-run announcements. |

Targets are normal-operation budgets. Hard ceilings are enforcement points.

## Alignment cost

Alignment is the real risk. Naive all-pairs block similarity is O(n×m). For the reference workload, 2,000 Manuscript A blocks × 2,000 Manuscript B blocks = 4,000,000 `rapidfuzz` comparisons before any token-level diff begins.

[Diff engine](./04-diff-engine.md) owns the algorithm. This document owns the cost envelope:

| Mitigation | Requirement |
|---|---|
| Anchor-first strategy | Hash normalized block text, match unique identical blocks first at zero similarity cost, pin the sequence, and align only the gaps between anchors. This turns common literary revisions into many small alignment problems instead of one 4,000,000-pair matrix. |
| Gap confinement | Compare an unmatched block only with unmatched blocks in the corresponding anchor-bounded gap. Do not invent a global positional band or fixed block window; [Diff engine](./04-diff-engine.md) specifies gaps, not banding. |
| Length-ratio prefilter | Reject implausible pairs before scoring when token counts are too far apart for a revision of one block into another, except when evaluating explicit `SPLIT` or `MERGED` concatenation candidates. |
| `rapidfuzz.process.extract` | Score in C++ with `score_cutoff=align_threshold` rather than calling scorers in Python loops; sub-threshold pairs are discarded before they reach Python. `process.cdist` would batch the whole matrix but requires NumPy, which is not worth adding for one call — see [Diff engine](./04-diff-engine.md). |
| Greedy assignment | Sort surviving candidate pairs by score, commit the highest-scoring available pair, remove both blocks, and repeat until no candidate clears `align_threshold`. Do not substitute a Hungarian assignment without a new ADR. |
| LIS move detection | After assignment, detect `MOVED` blocks from the longest increasing subsequence of B ordinals in A order. `move_threshold` controls whether a displaced pair is strong enough to report as a move. |

## Diff budget and the 202 path

`POST /api/v1/comparisons` computes inline only when the submitted witnesses are within the inline budget:

| Threshold | Behaviour |
|---|---|
| `a.metadata.block_count + b.metadata.block_count <= 4,000` and estimated total word tokens `<= 220,000` | Return `201 ComparisonResult` inline when all stage ceilings are met. |
| Total blocks `> 4,000` or estimated total word tokens `> 220,000` | Return `202 ComparisonAccepted` and compute outside the request-response path. |
| Total blocks `> 12,000` or estimated total word tokens `> 700,000` | Return `DIFF_BUDGET_EXCEEDED`. |
| Estimated serialized token payload `> 75 MB` before compression | Return `202 ComparisonAccepted` if otherwise allowed, and require windowed reads. |
| Estimated peak RSS `> 512 MB` for one comparison | Return `202 ComparisonAccepted` if a worker slot is available; otherwise return `RATE_LIMITED`. |

Refusing with `DIFF_BUDGET_EXCEEDED` is better than accepting a request that dies at a proxy timeout. The researcher receives a named ceiling and can reduce the witness size or change options.

## Payload size and windowing

The token-level JSON payload is much larger than the source text. For one reference witness, the source is about 600 KB. A serialized token such as `{"text":"example ","status":"UNCHANGED"}` is commonly 45-55 bytes once separators and ordinary word lengths are counted. At 100,000 word tokens per witness, the token-array arithmetic is:

| Quantity | Arithmetic | Approximate size |
|---|---:|---:|
| One witness token stream | 100,000 tokens × 45-55 bytes | 4.5-5.5 MB |
| `a_tokens` and `b_tokens` | 2 × 4.5-5.5 MB | 9.0-11.0 MB |
| Unified `tokens` | 100,000-200,000 token appearances × 45-55 bytes | 4.5-11.0 MB |
| Token arrays before block overhead | 300,000-400,000 token appearances × 45-55 bytes | 13.5-22.0 MB |
| Block, metrics, ids, dates, metadata, array separators, and escaping | About 2,000 blocks plus envelope fields | About 2-3 MB |
| Reference `ComparisonResult` before compression | Sum of above | About 16-25 MB |

That is roughly 13-21× the 1.2 MB combined source text for both witnesses. Repetitive JSON compresses well: gzip should reduce this payload by about 70-85%, and brotli should reduce it by about 75-90%.

This arithmetic assumes **one `Token` object per word, which is the maximum-fragmentation case** and therefore the correct basis for a budget. In practice a `Token` carries a contiguous run of same-status words, as [Data schema](./05-data-schema.md) specifies, so a real manuscript revision — which changes a small fraction of its words and leaves long unchanged runs — serializes to roughly 5 MB rather than 16-25 MB. Budgets are set from the ceiling; storage sizing in [Session storage](./07-session-storage.md) is set from the typical case. Both figures are correct for their purpose and must not be conflated.

Windowing is mandatory above these thresholds:

| Threshold | Behaviour |
|---|---|
| `total_blocks <= 2,500` and serialized `ComparisonResult <= 12 MB` before compression | Return complete `blocks` with `truncated: false`. |
| `total_blocks > 2,500` or serialized `ComparisonResult > 12 MB` before compression | Return the first 200 blocks, `truncated: true`, and the authoritative `total_blocks`. |
| Client needs more blocks | Fetch `GET /api/v1/comparisons/{comparison_id}/blocks?offset=&limit=`. Default `limit` is 200; maximum `limit` is 500. |

The initial window must include block 0 unless `?block=<index>` is requested. With a requested block, the initial window is centered on that block when possible.

## Memory handling on the backend

Uploads stream to `SpooledTemporaryFile`. The backend never holds both raw witnesses plus the full diff payload in memory simultaneously. Parsing, normalization, and tokenization should expose generators or iterators where practical, materializing only the `Document` and `DiffBlock` data required by storage and response construction.

| Memory item | Target |
|---|---:|
| Peak RSS per inline comparison | 256 MB |
| Hard peak RSS per comparison | 512 MB |
| Maximum concurrent inline comparisons per 2 GB worker | 3 |
| Reserved headroom per 2 GB worker | At least 512 MB for the event loop, SQLite, response buffers, and framework overhead. |

The concurrency cap follows the hard ceiling: 3 comparisons × 512 MB = 1,536 MB, leaving 512 MB headroom in a 2 GB worker. Additional requests return `202 ComparisonAccepted` if queued execution is available or `RATE_LIMITED` if it is not.

## Frontend rendering

The frontend uses `react-virtuoso` 4.18.11 because the comparison view has variable-height prose blocks. The chosen virtualizer provides automatic ResizeObserver measurement and an imperative handle for `scrollToIndex`, both required by [Components](./10-components.md).

| Rendering budget | Requirement |
|---|---|
| Rendered rows | Keep mounted rows under 120, including overscan, in **both** reading views. A synoptic row carries both witnesses, so this is 120 rows and not 120 per witness. This is a property of the view: the client loads every block of a windowed comparison, so nothing upstream caps how many rows a naive view would mount. |
| Printing | The one exception. Both views suspend virtualization for the duration of a print, because a virtualized list puts a fraction of the collation on paper with nothing on the page to say so. See [Design system](./09-design-system.md). |
| DOM nodes per rendered block | Target fewer than 250 nodes for a changed block and fewer than 40 nodes for an unchanged block by coalescing unchanged token runs. |
| Overscan | Expressed in pixels through `increaseViewportBy`, because that is the unit `react-virtuoso` takes and prose block heights are not known in advance. The default is 1200px, roughly a viewport of prose above and below. |
| `TokenSpan` memoization | Memoize by `text`, `status`, and announcement mode. Do not re-render token spans when only scroll position changes. |
| Connectors | Draw `BlockConnector` only for measured visible endpoints. |

Not virtualizing is not acceptable. A reference comparison can require at least 200,000 token spans across two panes before unified `tokens` and gutters are counted, and up to about 400,000 token appearances across all three streams in a heavily changed comparison. Rendering that many spans produces a hung tab on ordinary hardware and makes scroll synchronization impossible to keep responsive.

Virtualization and synchronized scrolling actively fight each other. The follower pane often has no measured height for the target block because the target is not mounted. The required solution is the two-phase anchor algorithm in [Components](./10-components.md): `scrollToIndex` to mount the anchor, then a measured correction after ResizeObserver reports height.

## SQLite performance

[Session storage](./07-session-storage.md) owns the schema. Performance depends on writing each comparison as a small number of bounded SQLite writes:

| Concern | Requirement |
|---|---|
| Write cost per comparison | One `documents` row per witness and one `comparisons` row per comparison. Large JSON fields are written once, not updated repeatedly during inline computation. |
| WAL | Use `journal_mode=WAL` and `synchronous=NORMAL` so readers do not block on the writer during ordinary comparison reads. |
| Single writer | SQLite still has one writer. Background comparison workers must serialize writes and use `busy_timeout=5000`. |
| Sweeper indexes | [Session storage](./07-session-storage.md) defines `idx_documents_expires_at` and `idx_comparisons_expires_at`; the sweeper must use them so expiry is an indexed range delete rather than a full scan. |
| Store size | Keep the active SQLite store under 5 GB. At an average compressed or compacted comparison footprint of 5 MB, that allows about 1,000 live reference comparisons. |
| Oversize rows | Windowed block storage is required when one `blocks_json` value would exceed 50 MB before compression or compaction. |

WAL files can grow during bursts. Checkpointing is part of the storage maintenance path, not the request path.

## Degradation ladder

Degradation proceeds in this order:

1. Return a full `ComparisonResult` with `truncated: false`.
2. Return a windowed `ComparisonResult` with `truncated: true`, `total_blocks`, and block pages from `GET /api/v1/comparisons/{comparison_id}/blocks?offset=&limit=`.
3. Disable move detection by setting effective `DiffOptions.detect_moves` to `false` and report that tradeoff in comparison metadata or warnings owned by the API contract.
4. Disable `CHARACTER` granularity and use `Granularity.WORD`.
5. Return block-level-only changed regions for oversize aligned pairs while preserving `DiffBlock.status` and `BlockMetrics`.
6. Refuse with `DIFF_BUDGET_EXCEEDED`.

This order is a feature. The researcher is told what was traded away, and the tool never silently returns a worse answer.

## Measurement

Every comparison records the facts needed to enforce these budgets:

| Measurement | Purpose |
|---|---|
| Per-stage timings | Parse, normalize, tokenize, align, word-diff, serialize, transfer, and first render. |
| Peak RSS | Enforces the 256 MB target and 512 MB hard ceiling per comparison. |
| Payload bytes | Records pre-compression and post-compression `ComparisonResult` sizes. |
| Block and token counts | Explains why a comparison was inline, accepted, windowed, degraded, or refused. |
| Candidate pair counts | Proves that alignment avoided the full O(n×m) matrix where possible. |
| Browser render metrics | Tracks first render, mounted row count, token span count, and scroll-sync correction frames. |

The standing benchmark corpus described in [Testing strategy](./13-testing-strategy.md) guards these budgets. It must include small identical witnesses, small completely different witnesses, the 100,000-word reference workload, a moved-section workload, a split-and-merged workload, and an OCR-required PDF fixture.
