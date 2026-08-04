# Data schema

The normative wire contract between the diff engine and every consumer: Pydantic models, the JSON payload, and its TypeScript mirror.

**Status:** Draft

**Related:** [Diff engine](./04-diff-engine.md) · [Normalization](./03-normalization.md) · [API reference](./06-api-reference.md) · [Components](./10-components.md) · [Testing strategy](./13-testing-strategy.md)

---

## Principles

**The payload is the API.** It is a documented, stable artifact that other tools in a digital-humanities pipeline can consume without knowing anything about palimpsest's internals. It is designed to be read by a program, archived, and diffed against itself across versions.

**JSON is `snake_case` and matches the Python field names exactly.** No aliases, no camelCase transformation at the boundary. Aliasing buys a small amount of JavaScript idiom and costs a permanent translation layer that must be kept correct in two languages; the trade is not worth it. TypeScript consumers use `snake_case` property names and this is intentional.

**The client renders, it does not compute.** Every number a reader sees is present in the payload. The client must never derive metrics, filter token streams, or infer block relationships — if the UI needs it, the payload carries it. This follows from [ADR-0004](./adr/0004-server-side-diff-computation.md) and is what makes the golden-corpus tests in [testing](./13-testing-strategy.md) meaningful: they pin the entire user-visible result.

**Fields reserved for future capability are present from day one.** `Block.confidence`, `Block.bbox`, and `DocumentMetadata.ocr_confidence` are `null` for every parser that ships in v1. They exist now so that adding the OCR parser described in [ingestion](./02-ingestion-and-parsers.md) is not a schema change.

---

## Enumerations

```python
from enum import StrEnum

class TokenStatus(StrEnum):
    UNCHANGED = "UNCHANGED"
    INSERTION = "INSERTION"
    DELETION  = "DELETION"

class BlockStatus(StrEnum):
    UNCHANGED = "UNCHANGED"   # aligned pair, byte-identical after normalization
    MODIFIED  = "MODIFIED"    # aligned pair, differing tokens
    INSERTED  = "INSERTED"    # present only in Manuscript B
    DELETED   = "DELETED"     # present only in Manuscript A
    MOVED     = "MOVED"       # aligned pair outside the longest increasing subsequence
    SPLIT     = "SPLIT"       # one A block became several B blocks
    MERGED    = "MERGED"      # several A blocks became one B block

class BlockKind(StrEnum):
    PARAGRAPH  = "PARAGRAPH"
    HEADING    = "HEADING"
    VERSE_LINE = "VERSE_LINE"
    QUOTE      = "QUOTE"
    LIST_ITEM  = "LIST_ITEM"
    ARTIFACT   = "ARTIFACT"   # running head, folio number, footer — excluded from the diff by default

class SourceFormat(StrEnum):
    TXT = "TXT"; MARKDOWN = "MARKDOWN"; DOCX = "DOCX"; PDF = "PDF"; OCR = "OCR"

class Granularity(StrEnum):
    WORD = "WORD"; CHARACTER = "CHARACTER"
```

`TokenStatus` has exactly three members and will not grow. A token either survived, arrived, or left; anything richer belongs at block level. Keeping this enum closed is what allows the client's `TokenSpan` to be a trivially fast component, which matters when a page holds tens of thousands of them.

`SourceFormat.OCR` is defined and reachable by no v1 parser. It is reserved so the roadmap does not require a migration.

---

## Document models

Produced by [ingestion](./02-ingestion-and-parsers.md) and [normalization](./03-normalization.md); consumed by the diff engine.

```python
class BoundingBox(BaseModel):
    page: int
    x0: float; y0: float; x1: float; y1: float

class Block(BaseModel):
    id: str                          # stable within its Document
    index: int                       # 0-based ordinal; the "line number" shown in the gutter
    kind: BlockKind
    text: str                        # normalized
    style: str | None = None         # source style name, e.g. "Heading 1" — diagnostic only
    page: int | None = None          # 1-based, PDF only
    char_start: int                  # offset into the reconstructed full text
    char_end: int
    confidence: float | None = None  # reserved for OCR
    bbox: BoundingBox | None = None  # reserved for OCR

class IngestionWarning(BaseModel):
    code: str
    message: str
    block_id: str | None = None

class DocumentMetadata(BaseModel):
    word_count: int
    block_count: int
    char_count: int
    detected_language: str | None = None   # BCP 47
    parser_name: str
    parser_version: str
    ocr_confidence: float | None = None

class Document(BaseModel):
    id: str
    title: str
    source_format: SourceFormat
    blocks: list[Block]
    metadata: DocumentMetadata
    warnings: list[IngestionWarning] = []

class DocumentSummary(BaseModel):
    """A Document without its blocks — embedded in ComparisonResult."""
    id: str
    title: str
    source_format: SourceFormat
    metadata: DocumentMetadata
    warnings: list[IngestionWarning] = []
```

`index` is the ordinal the UI displays in its change gutter. It is a **block index, not a rendered line number** — prose reflows with viewport width, so visual lines are not addressable and never appear in this schema. See [components](./10-components.md).

`char_start` and `char_end` are offsets into the document's reconstructed full text. Nothing in v1 reads them; they exist because block-anchored annotation and TEI export both require stable source offsets, and adding them later would invalidate every stored comparison.

`DocumentSummary` exists so that `ComparisonResult` can describe both witnesses without carrying two full copies of the source text alongside the diff — a saving of roughly a third of the payload for the reference workload in [performance and scale](./11-performance-and-scale.md).

### Identifier conventions

All identifiers are opaque strings and consumers must treat them as such — nothing may parse an id to recover structure. The formats below are nonetheless normative, because consistent prefixes make logs, stored payloads, and bug reports legible at a glance.

| Entity | Format | Example |
|---|---|---|
| Document | `doc_` + 128-bit URL-safe random | `doc_rV3xYlKq9n4Q` |
| Comparison | `cmp_` + 128-bit URL-safe random | `cmp_P7nR4tV9xA2mQ6s` |
| Block in Manuscript A | `blk_a_` + zero-padded `index` | `blk_a_0000` |
| Block in Manuscript B | `blk_b_` + zero-padded `index` | `blk_b_0000` |
| Diff block | `dbk_` + zero-padded sequence | `dbk_0001` |
| Split/merge group | `grp_` + zero-padded sequence | `grp_0001` |

Document and comparison ids are **randomly generated with at least 128 bits of entropy**, because unguessability is the entire access-control model in v1 — see [session storage](./07-session-storage.md). Block, diff-block, and group ids are deterministic sequences scoped to their parent, which is what allows the golden-corpus tests in [testing](./13-testing-strategy.md) to compare whole payloads byte for byte after masking only the two random ids and the timestamps.

---

## Diff models

```python
class Token(BaseModel):
    text: str            # surface form of a contiguous run, including trailing whitespace
    status: TokenStatus

class BlockMetrics(BaseModel):
    similarity: float    # 0.0–1.0
    edit_count: int      # insertions + deletions
    insertions: int
    deletions: int
    churn: float         # 0.0–1.0

class DiffBlock(BaseModel):
    id: str
    status: BlockStatus
    kind: BlockKind
    a_index: int | None = None       # null when INSERTED
    b_index: int | None = None       # null when DELETED
    a_block_id: str | None = None
    b_block_id: str | None = None
    tokens: list[Token]              # unified stream
    a_tokens: list[Token]            # UNCHANGED + DELETION
    b_tokens: list[Token]            # UNCHANGED + INSERTION
    metrics: BlockMetrics
    move_distance: int | None = None # signed block displacement; non-null only when MOVED
    group_id: str | None = None      # shared by all members of a SPLIT or MERGED group

class DiffMetrics(BaseModel):
    similarity: float
    edit_count: int
    insertions: int
    deletions: int
    unchanged_tokens: int
    churn: float
    blocks_moved: int
    blocks_split: int
    blocks_merged: int
    a_word_count: int
    b_word_count: int

class DiffOptions(BaseModel):
    granularity: Granularity = Granularity.WORD
    detect_moves: bool = True
    align_threshold: float = 0.50
    move_threshold: float = 0.75
    ignore_case: bool = False
    ignore_punctuation: bool = False
    normalize_whitespace: bool = True

class ComparisonResult(BaseModel):
    comparison_id: str
    created_at: datetime
    expires_at: datetime
    a: DocumentSummary
    b: DocumentSummary
    blocks: list[DiffBlock]
    metrics: DiffMetrics
    options: DiffOptions
    truncated: bool = False   # true when blocks is a window, not the whole comparison
    total_blocks: int

class BlockPage(BaseModel):
    blocks: list[DiffBlock]
    offset: int
    limit: int
    total_blocks: int
```

### A `Token` is a run, and the counts are in words

One subtlety deserves stating plainly, because it is the easiest thing in this schema to get wrong.

The *unit of diffing* is a token — a word plus its trailing whitespace, per [the diff engine](./04-diff-engine.md). The *payload object* named `Token` carries a **contiguous run of one or more such tokens that share a status**, because that is what `diff_match_patch` naturally emits and what the client naturally renders. A single `Token` with `text` of `"cat sat "` is two words in one object.

This is a deliberate trade. Emitting one object per word would triple the payload and produce one DOM node per word — a hundred thousand of them for the reference workload — for no reader-visible benefit, since adjacent words of identical status are styled identically anyway.

The consequence for metrics: **`insertions`, `deletions`, `edit_count`, `unchanged_tokens`, `a_word_count`, and `b_word_count` are all counts of words, never counts of `Token` objects.** A client that computes `block.tokens.filter(t => t.status === "INSERTION").length` will get a different and wrong number. It should not be computing them at all — the payload carries them.

### Invariants

These hold for every payload the engine emits and are asserted directly in [testing](./13-testing-strategy.md):

1. **Pane reconstruction (exact).** `"".join(t.text for t in a_tokens)` reproduces Manuscript A's block text character for character; likewise `b_tokens` for B.
2. **Unified projection (word-for-word).** `tokens` filtered of `INSERTION` agrees with `a_tokens` on the word sequence, and filtered of `DELETION` agrees with `b_tokens`. It is deliberately *not* required to agree on whitespace — see the note below.
3. `a_tokens` contains no `INSERTION`; `b_tokens` contains no `DELETION`.
4. `metrics.edit_count == metrics.insertions + metrics.deletions`, at both block and document level.
5. `a_index` is `null` if and only if `status == INSERTED`. `b_index` is `null` if and only if `status == DELETED`.
6. `move_distance` is non-null if and only if `status == MOVED`.
7. `group_id` is non-null if and only if `status` is `SPLIT` or `MERGED`, and every member of a group shares one value.
8. `blocks` is ordered for reading: by `b_index` where present, otherwise positioned at the deleted block's place in the A sequence.
9. When `truncated` is `false`, `len(blocks) == total_blocks`.

Invariant 1 is the strongest of these. It means the payload is lossless with respect to both witnesses, so a client — or an archival consumer years later — can reconstruct either manuscript from the comparison alone.

### Why the unified stream is not byte-exact

Invariant 2 is weaker than invariant 1, and deliberately so. The unified `tokens` array is a *third rendering*, not a copy of either pane, and two things stop it from reproducing both witnesses byte for byte at once.

It interleaves runs that were never adjacent in either witness. A deletion followed directly by an insertion — Manuscript A's `alpha` replaced by Manuscript B's `beta` — concatenates to `alphabeta` unless a separator is inserted. The engine therefore guarantees that adjacent runs never fuse, at the cost of introducing whitespace that appears in neither witness.

And under `normalize_whitespace`, which is on by default, two runs compare equal while carrying different trailing whitespace: a word that ends a block in one witness sits mid-block in the other. The engine keeps each pane's own spacing in `a_tokens` and `b_tokens`, so the unified stream cannot match both.

The practical consequence for clients: **render from `a_tokens` and `b_tokens` in synoptic view and from `tokens` in unified view. Do not reconstruct one from the other.** Word counts are unaffected, because a separator contributes no words — which is why every metric in this schema remains exact.

### Ordering

`blocks` arrives in reading order and the client renders it as given; it must never re-sort. Reading order is B's order, because Manuscript B is the later state of the text and the reader is following its shape. `DELETED` blocks have no B ordinal, so they are interleaved at the position their A neighbours imply — which is why the array cannot be reconstructed from `b_index` alone and why ordering is fixed by this document rather than left to the client.

---

## Normative payload example

A three-block comparison exercising an unchanged heading, a modified paragraph, and a split. This example is valid against every model above and every invariant.

```json
{
  "comparison_id": "cmp_7Kx9mQ2vL4nR8tYw",
  "created_at": "2026-08-04T12:00:00Z",
  "expires_at": "2026-08-11T12:00:00Z",
  "a": {
    "id": "doc_3Hn5pQ8rT2vX",
    "title": "Crossing — draft 1",
    "source_format": "DOCX",
    "metadata": {
      "word_count": 21,
      "block_count": 3,
      "char_count": 99,
      "detected_language": "en",
      "parser_name": "DocxParser",
      "parser_version": "1.0.0",
      "ocr_confidence": null
    },
    "warnings": []
  },
  "b": {
    "id": "doc_9Wq4sN7mK3bZ",
    "title": "Crossing — draft 2",
    "source_format": "DOCX",
    "metadata": {
      "word_count": 19,
      "block_count": 4,
      "char_count": 96,
      "detected_language": "en",
      "parser_name": "DocxParser",
      "parser_version": "1.0.0",
      "ocr_confidence": null
    },
    "warnings": []
  },
  "options": {
    "granularity": "WORD",
    "detect_moves": true,
    "align_threshold": 0.5,
    "move_threshold": 0.75,
    "ignore_case": false,
    "ignore_punctuation": false,
    "normalize_whitespace": true
  },
  "metrics": {
    "similarity": 0.8,
    "edit_count": 8,
    "insertions": 3,
    "deletions": 5,
    "unchanged_tokens": 16,
    "churn": 0.2,
    "blocks_moved": 0,
    "blocks_split": 2,
    "blocks_merged": 0,
    "a_word_count": 21,
    "b_word_count": 19
  },
  "truncated": false,
  "total_blocks": 4,
  "blocks": [
    {
      "id": "dbk_0001",
      "status": "UNCHANGED",
      "kind": "HEADING",
      "a_index": 0,
      "b_index": 0,
      "a_block_id": "blk_a_0000",
      "b_block_id": "blk_b_0000",
      "tokens": [{ "text": "Chapter One", "status": "UNCHANGED" }],
      "a_tokens": [{ "text": "Chapter One", "status": "UNCHANGED" }],
      "b_tokens": [{ "text": "Chapter One", "status": "UNCHANGED" }],
      "metrics": {
        "similarity": 1.0, "edit_count": 0, "insertions": 0,
        "deletions": 0, "churn": 0.0
      },
      "move_distance": null,
      "group_id": null
    },
    {
      "id": "dbk_0002",
      "status": "MODIFIED",
      "kind": "PARAGRAPH",
      "a_index": 1,
      "b_index": 1,
      "a_block_id": "blk_a_0001",
      "b_block_id": "blk_b_0001",
      "tokens": [
        { "text": "The ",     "status": "UNCHANGED" },
        { "text": "black ",   "status": "INSERTION" },
        { "text": "cat sat ", "status": "UNCHANGED" },
        { "text": "on ",      "status": "DELETION"  },
        { "text": "upon ",    "status": "INSERTION" },
        { "text": "the mat.", "status": "UNCHANGED" }
      ],
      "a_tokens": [
        { "text": "The ",     "status": "UNCHANGED" },
        { "text": "cat sat ", "status": "UNCHANGED" },
        { "text": "on ",      "status": "DELETION"  },
        { "text": "the mat.", "status": "UNCHANGED" }
      ],
      "b_tokens": [
        { "text": "The ",     "status": "UNCHANGED" },
        { "text": "black ",   "status": "INSERTION" },
        { "text": "cat sat ", "status": "UNCHANGED" },
        { "text": "upon ",    "status": "INSERTION" },
        { "text": "the mat.", "status": "UNCHANGED" }
      ],
      "metrics": {
        "similarity": 0.8519, "edit_count": 3, "insertions": 2,
        "deletions": 1, "churn": 0.2308
      },
      "move_distance": null,
      "group_id": null
    },
    {
      "id": "dbk_0003",
      "status": "SPLIT",
      "kind": "PARAGRAPH",
      "a_index": 2,
      "b_index": 2,
      "a_block_id": "blk_a_0002",
      "b_block_id": "blk_b_0002",
      "tokens": [{ "text": "It was a long crossing. ", "status": "UNCHANGED" }],
      "a_tokens": [{ "text": "It was a long crossing. ", "status": "UNCHANGED" }],
      "b_tokens": [{ "text": "It was a long crossing. ", "status": "UNCHANGED" }],
      "metrics": {
        "similarity": 1.0, "edit_count": 0, "insertions": 0,
        "deletions": 0, "churn": 0.0
      },
      "move_distance": null,
      "group_id": "grp_0001"
    },
    {
      "id": "dbk_0004",
      "status": "SPLIT",
      "kind": "PARAGRAPH",
      "a_index": 2,
      "b_index": 3,
      "a_block_id": "blk_a_0002",
      "b_block_id": "blk_b_0003",
      "tokens": [
        { "text": "The waves were grey ",    "status": "UNCHANGED" },
        { "text": "from the first morning ", "status": "DELETION"  },
        { "text": "throughout.",             "status": "INSERTION" }
      ],
      "a_tokens": [
        { "text": "The waves were grey ",    "status": "UNCHANGED" },
        { "text": "from the first morning ", "status": "DELETION"  }
      ],
      "b_tokens": [
        { "text": "The waves were grey ", "status": "UNCHANGED" },
        { "text": "throughout.",          "status": "INSERTION" }
      ],
      "metrics": {
        "similarity": 0.5556, "edit_count": 5, "insertions": 1,
        "deletions": 4, "churn": 0.3846
      },
      "move_distance": null,
      "group_id": "grp_0001"
    }
  ]
}
```

Two details in this example are worth drawing out. The split group shares `a_block_id` across both members — they came from one A block — and shares a `group_id` so the client can draw a single connector. And `dbk_0003` reports zero edits: the author split a paragraph without changing a word there, which the payload states plainly rather than dressing up as a rewrite.

---

## TypeScript mirror

The client's types must agree with the models above exactly. They are **generated from the OpenAPI schema in CI**, not hand-maintained — hand-written mirrors drift, and a drift here is a silent rendering bug rather than a loud failure. The generated output is committed so that reviewers can see schema changes in a diff. [Testing](./13-testing-strategy.md) specifies the contract check that fails the build when the committed types no longer match the generated ones.

```ts
export type TokenStatus = "UNCHANGED" | "INSERTION" | "DELETION";

export type BlockStatus =
  | "UNCHANGED" | "MODIFIED" | "INSERTED" | "DELETED"
  | "MOVED" | "SPLIT" | "MERGED";

export type BlockKind =
  | "PARAGRAPH" | "HEADING" | "VERSE_LINE" | "QUOTE" | "LIST_ITEM" | "ARTIFACT";

export type SourceFormat = "TXT" | "MARKDOWN" | "DOCX" | "PDF" | "OCR";
export type Granularity = "WORD" | "CHARACTER";

export interface Token { text: string; status: TokenStatus; }

export interface BlockMetrics {
  similarity: number; edit_count: number;
  insertions: number; deletions: number; churn: number;
}

export interface DiffBlock {
  id: string;
  status: BlockStatus;
  kind: BlockKind;
  a_index: number | null;
  b_index: number | null;
  a_block_id: string | null;
  b_block_id: string | null;
  tokens: Token[];
  a_tokens: Token[];
  b_tokens: Token[];
  metrics: BlockMetrics;
  move_distance: number | null;
  group_id: string | null;
}

export interface DiffMetrics {
  similarity: number; edit_count: number;
  insertions: number; deletions: number; unchanged_tokens: number;
  churn: number;
  blocks_moved: number; blocks_split: number; blocks_merged: number;
  a_word_count: number; b_word_count: number;
}

export interface DiffOptions {
  granularity: Granularity;
  detect_moves: boolean;
  align_threshold: number;
  move_threshold: number;
  ignore_case: boolean;
  ignore_punctuation: boolean;
  normalize_whitespace: boolean;
}

export interface DocumentMetadata {
  word_count: number; block_count: number; char_count: number;
  detected_language: string | null;
  parser_name: string; parser_version: string;
  ocr_confidence: number | null;
}

export interface IngestionWarning {
  code: string; message: string; block_id: string | null;
}

export interface DocumentSummary {
  id: string; title: string; source_format: SourceFormat;
  metadata: DocumentMetadata; warnings: IngestionWarning[];
}

export interface ComparisonResult {
  comparison_id: string;
  created_at: string;   // RFC 3339
  expires_at: string;   // RFC 3339
  a: DocumentSummary;
  b: DocumentSummary;
  blocks: DiffBlock[];
  metrics: DiffMetrics;
  options: DiffOptions;
  truncated: boolean;
  total_blocks: number;
}

export interface BlockPage {
  blocks: DiffBlock[];
  offset: number; limit: number; total_blocks: number;
}
```

---

## Size characteristics

A token-level JSON payload is considerably larger than the prose it describes. The fixed overhead of one `Token` object is 33 bytes — `{"text":"","status":"UNCHANGED"},` — on top of the text it carries, and the three token streams mean unchanged prose is serialised three times over.

How much that costs depends entirely on **how fragmented the diff is**, because a `Token` holds a contiguous run rather than a single word:

| Case | Token objects per stream | Uncompressed `ComparisonResult` |
|---|---:|---:|
| Maximum fragmentation — every word alternates status | ~100,000 | 16–25 MB |
| Typical revision — a few thousand change sites, unchanged prose coalescing into long runs | ~10,000 | ~5 MB |
| Identical witnesses — one run per block | ~2,000 | ~2 MB |

The 16–25 MB figure is a **ceiling, not an expectation**; [performance and scale](./11-performance-and-scale.md) derives it in full and uses it to set budgets, which is the right way to size a system. A real manuscript revision changes a small fraction of its words, so unchanged text coalesces and the payload lands near the middle row — which is also why [session storage](./07-session-storage.md) budgets around 5 MB per stored comparison.

The mitigations are specified in [performance and scale](./11-performance-and-scale.md): this JSON is highly repetitive and compresses by 75–90% under brotli, `DocumentSummary` keeps the source text out of the envelope, and above a defined block count the client stops receiving `blocks` inline and pages through `GET /api/v1/comparisons/{comparison_id}/blocks` instead, with `truncated` and `total_blocks` telling it that it must.

Emitting all three token streams is a deliberate trade of bytes for client simplicity. It is revisited in performance work before it is revisited here.

---

## Evolution

The schema is versioned with the API path (`/api/v1`). Within a major version, only additive changes are permitted: new optional fields with defaults, and new members of `BlockStatus`, `BlockKind`, or `SourceFormat`. Clients must ignore unknown fields and must degrade gracefully on an unrecognised enum member rather than failing to render.

Removing a field, renaming one, changing a type, or removing an enum member requires a new major version. `TokenStatus` is closed and is not expected to change at all.

Because [session storage](./07-session-storage.md) is a cache with a deadline rather than a system of record, stored payloads never need migrating — they expire. That is a genuine and deliberate advantage of the storage design.
