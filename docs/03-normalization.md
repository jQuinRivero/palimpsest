This document specifies the normalization stage that turns parser output into the canonical `Document` form consumed by alignment and diffing.

**Status:** Draft

**Related:** [Specification index](./README.md) · [Ingestion and parsers](./02-ingestion-and-parsers.md) · [Diff engine](./04-diff-engine.md) · [Edge cases](./12-edge-cases.md) · [Testing strategy](./13-testing-strategy.md)

## Why normalization is a separate stage

Parsers produce format-flavoured text. `PlainTextParser` sees decoded lines, `DocxParser` sees Word paragraphs and styles, and `PdfPlumberParser` sees positioned characters. The diff engine needs one canonical form so that alignment means the same thing regardless of whether Manuscript A is `DOCX` and Manuscript B is `PDF`.

Normalization is therefore a separate pure stage in `backend/app/services/ingestion/normalize.py`. It must be deterministic, idempotent, and side-effect free: normalizing an already-normalized `Document` must produce the same `Document`, and the same parser output plus normalization options must always produce the same result. It must also be auditable: a researcher must be able to understand why two visually identical passages did or did not compare equal.

## The canonical `Document` model

The ingestion boundary is the following Pydantic v2 model family. Field names are `snake_case` in Python and JSON.

```python
IngestionWarning:    code: str; message: str; block_id: str | None
BoundingBox:         page: int; x0: float; y0: float; x1: float; y1: float

Block:               id: str; index: int; kind: BlockKind; text: str
                     style: str | None; page: int | None
                     char_start: int; char_end: int
                     confidence: float | None; bbox: BoundingBox | None

DocumentMetadata:    word_count: int; block_count: int; char_count: int
                     detected_language: str | None; parser_name: str; parser_version: str
                     ocr_confidence: float | None

Document:            id: str; title: str; source_format: SourceFormat
                     blocks: list[Block]; metadata: DocumentMetadata; warnings: list[IngestionWarning]
```

| Field | Commentary |
|---|---|
| `Document.id` | Unguessable document identifier assigned by ingestion or storage. |
| `Document.title` | Researcher-supplied title when available; otherwise a stable title derived from source metadata or filename. |
| `Document.source_format` | Exact `SourceFormat` member: `TXT`, `MARKDOWN`, `DOCX`, `PDF`, or future `OCR`. |
| `Document.blocks` | Ordered canonical blocks. `ARTIFACT` blocks may be present but are excluded from the diff by default. |
| `Document.metadata` | Counts and parser provenance for display, diagnostics, and reproducibility. |
| `Document.warnings` | Recoverable extraction and normalization issues that the UI can surface. |
| `Block.id` | Stable within one `Document`; used by warnings, annotations, and diff references. |
| `Block.index` | Zero-based order after normalization. |
| `Block.kind` | Exact `BlockKind`: `PARAGRAPH`, `HEADING`, `VERSE_LINE`, `QUOTE`, `LIST_ITEM`, or `ARTIFACT`. |
| `Block.text` | Canonical text used for alignment and tokenization. |
| `Block.style` | Parser-supplied style name when meaningful, such as a DOCX paragraph style. |
| `Block.page` | Source page number when known, mainly for PDF and future OCR. |
| `Block.char_start`, `Block.char_end` | Half-open offsets into the reconstructed full text formed by joining normalized blocks in order. They are retained for citation, source mapping, future annotation, and explaining normalization decisions. |
| `Block.confidence` | Reserved for OCR; `None` for v1 non-OCR parsers. |
| `Block.bbox` | Reserved for OCR and positional source mapping; `None` when no bounding box is available. |
| `BoundingBox.page`, `x0`, `y0`, `x1`, `y1` | Page and coordinates of an OCR or positional text region. |
| `DocumentMetadata.word_count` | Count after normalization, aligned with `WORD` tokenization expectations. |
| `DocumentMetadata.block_count` | Number of blocks in `Document.blocks`. |
| `DocumentMetadata.char_count` | Character count after normalization. |
| `DocumentMetadata.detected_language` | Optional language hint; not used for semantic transformation. |
| `DocumentMetadata.parser_name`, `parser_version` | Exact parser provenance for reproducible ingestion. |
| `DocumentMetadata.ocr_confidence` | Reserved for OCR aggregate confidence. |
| `IngestionWarning.code`, `message`, `block_id` | Machine-readable warning code, human-readable explanation, and optional affected block. |

`char_start` and `char_end` are offsets into reconstructed full text, not byte offsets into the original source. They use Python string indexing semantics: `char_start` is inclusive, `char_end` is exclusive, and `char_end - char_start == len(Block.text)`. The reconstructed full text is the normalized block texts in order with the canonical separator used by ingestion. Retaining these offsets lets the UI cite a passage, map an annotation back to a block range, and explain that a displayed difference came from normalization rather than source bytes.

## The normalization pipeline

Normalization is ordered. Later stages rely on invariants established by earlier stages.

### 1. Encoding resolution and Unicode normalization to NFC

Encoding resolution happens before semantic block decisions. Bytes are decoded by the parser using format-appropriate rules; text then normalizes to Unicode NFC.

NFC is required rather than NFD because decomposed and precomposed spellings of the same accented character should compare equal after normalization. This matters enormously for French, Spanish, Vietnamese, and other source texts where accents are meaningful but may be represented differently by export tools.

| Before | After |
|---|---|
| `Cafe\u0301` (`e` plus combining accent) | `Café` |
| `sen\u0303or` (`n` plus combining tilde) | `señor` |

Rationale: two visually identical passages must not differ merely because one witness used decomposed Unicode and the other used precomposed characters.

### 2. Ligature and typographic folding

Ligatures are folded by default:

| Before | After |
|---|---|
| `ﬁrst ﬂower` | `first flower` |

This corrects a common extraction artifact where PDF fonts encode printed ligatures as single Unicode code points. Without this fold, `ﬁrst` and `first` would tokenize differently even though the prose is the same.

Curly quote and dash folding is optional and off by default. It belongs to `DiffOptions`, not silent normalization.

| Optional fold | Before | After |
|---|---|---|
| Curly apostrophe | `don’t` | `don't` |
| Curly quotation marks | `“quoted”` | `"quoted"` |
| En dash | `Paris–London` | `Paris-London` |

The trade-off is scholarly. A researcher studying compositor practice may care that Manuscript A uses `’` and Manuscript B uses `'`, or that one witness uses an em dash where another uses a hyphen. `palimpsest` must not erase that evidence by default. The default reports the textual marks as written; an option may collapse them for a broader prose comparison.

### 3. Whitespace normalization

Whitespace normalization makes layout-neutral spacing comparable while preserving block boundaries.

Rules:

1. Normalize line endings to `\n`.
2. Strip trailing whitespace.
3. Collapse internal runs of spaces and tabs to one space where the parser has already established prose flow.
4. Preserve blank lines long enough for paragraph and verse decisions, then remove them from final `Block.text`.

| Before | After |
|---|---|
| `This  is\t spaced.  ` | `This is spaced.` |
| `Line one\r\nLine two` | `Line one\nLine two` |

Rationale: spacing introduced by export tools should not dominate the diff, but spacing that marks block boundaries must survive until segmentation.

### 4. Soft line-break reflow

PDFs and plain text exports often break lines for layout:

```text
It was the best of times, it was the worst
of times, it was the age of wisdom.
```

The normalized paragraph is:

```text
It was the best of times, it was the worst of times, it was the age of wisdom.
```

Reflow joins soft line breaks when the evidence points to layout rather than authorial structure. The heuristic considers:

| Signal | Interpretation |
|---|---|
| Blank line | Hard paragraph break; do not reflow across it. |
| Indentation change | Likely new paragraph, quote, or verse; avoid joining unless the parser already identified one block. |
| Terminal punctuation | A line ending in `.`, `?`, `!`, `:`, or `;` is less likely to need joining, though not conclusive. |
| Capitalisation of the next line | A lowercase next line often indicates a soft break; an uppercase next line may indicate a new sentence or heading. |
| Short-line detection for verse | Repeated short lines with poetic cadence are likely `VERSE_LINE` blocks, not wrapped prose. |

`VERSE_LINE` blocks are explicitly exempt from reflow. A poem must not become a paragraph merely because its lines lack terminal punctuation.

| Before | After |
|---|---|
| A quatrain of four consistently measured lines | Four `VERSE_LINE` blocks, one per line, unchanged |
| `The argument continues without\ninterruption across the margin.` | One `PARAGRAPH` block: `The argument continues without interruption across the margin.` |

A two-line fragment is **not** enough evidence. Two lines carry no reliable measure, and the pairs that superficially resemble a couplet — a heading above its first line, a speaker label, a date over an address — are far more common in real uploads than actual verse. Detection needs at least three lines.

### 5. Dehyphenation

Dehyphenation handles line-end hyphens introduced by layout. See [Edge cases](./12-edge-cases.md) for the full treatment of hyphens and PDF noise. The policy here is fixed:

- `dehyphen` is rejected because it is GPL-3.0 and stale.
- `palimpsest` uses a deterministic rule plus a lexicon check.
- Non-obvious joins emit an `IngestionWarning` identifying the affected block so the UI can explain the normalization decision.

Worked examples:

| Before | Decision | After |
|---|---|---|
| `inter-\nnational` | Join because `international` is lexicon-valid. | `international` |
| `well-\nknown` | Keep because the hyphen may be lexical. | `well-known` |
| `re-\nenter` | Keep unless the lexicon and rule set prove the joined form intended by the source. | `re-enter` |

Recording non-obvious decisions matters. The UI must be able to explain that two paragraphs differ only in hyphenation when one witness has `inter-\nnational` and the other has `international`, without implying that the canonical `Document` stores a separate reversible edit log.

### 6. Block segmentation and `BlockKind` assignment

After text-level normalization, ingestion creates `Block` objects and assigns `BlockKind`.

| Evidence | `BlockKind` |
|---|---|
| Parser style `Heading 1` through `Heading 9`, Markdown ATX heading, Markdown setext heading | `HEADING` |
| Three or more lines of consistent short measure, each a phrase | `VERSE_LINE` |
| DOCX `Quote` or `Intense Quote`, Markdown blockquote | `QUOTE` |
| DOCX `List *`, Markdown list item | `LIST_ITEM` |
| Running head, folio number, footer | `ARTIFACT` |
| Default prose | `PARAGRAPH` |

### Verse segmentation

A block judged to be verse is split into one `VERSE_LINE` block per line, for every format. This is not cosmetic. Blocks are the unit of alignment, so a stanza-sized block reports a single revised word as a wholly modified stanza, and hides a transposed line entirely — moves are detected *between* blocks, never inside one. Line-level blocks are what let a reordered line read as `MOVED` with no wording change at all.

Only unclassified prose is eligible. A block the parser has already called a heading, quote, list item or artifact keeps that kind: a parser that knows outranks a heuristic that guesses.

**The bias is deliberately toward prose**, because the two errors are not symmetric. A missed poem leaves the previous behaviour intact. A misjudged paragraph is shattered into blocks that nobody reading the comparison can distinguish from structure the author wrote. Two rules follow:

| Rule | What it rejects |
|---|---|
| Lines must sit well below any normal prose measure, and consistently so | Narrow-column typeset prose, which is also consistent but sits *at* the measure |
| The median line must be a phrase rather than a single word | A column of figures, an address block, a list of one-word items, a run of initials — all perfectly consistent, none of them verse |

The second rule earns its place: without it, `A\nB\nC` is read as a poem.

Detection carries an `IngestionWarning` (`VERSE_SEGMENTED`) rather than being applied silently. Deciding a text is verse changes the unit of comparison, and a researcher must be able to see that the tool made that call — most of all when it made it wrongly.

Verse whose lines run long — much blank verse — will not be detected, and is left as prose. That is the conservative bias working as intended rather than a defect to be tuned away without evidence.

Worked example:

```markdown
## Preface

> I write under correction.

The main text begins here.
```

becomes:

| `index` | `kind` | `text` |
|---:|---|---|
| 0 | `HEADING` | `Preface` |
| 1 | `QUOTE` | `I write under correction.` |
| 2 | `PARAGRAPH` | `The main text begins here.` |

### 7. `ARTIFACT` classification

`ARTIFACT` blocks are extracted text that should not participate in the diff by default: running heads, folio numbers, and footers. They remain in `Document.blocks` because they are part of the source evidence and may support citation or diagnostics.

The main heuristic is repetition in page position. A short span that appears on multiple pages in the same top or bottom band, with stable horizontal alignment, is likely an artifact. A bare digit or roman numeral near the outer bottom margin is likely a folio number. `PdfPlumberParser` has the strongest evidence because it sees character positions; `PyPdfParser` may classify fewer artifacts.

| Extracted page text | Classification |
|---|---|
| `CHAPTER IV` at the top center of five consecutive pages | `ARTIFACT` |
| `127` at the bottom outside corner | `ARTIFACT` |
| `Chapter IV` once in the main flow before a paragraph | `HEADING` |

## Determinism and auditability

Every normalization that alters text must be recorded as an `IngestionWarning` or be reconstructible from deterministic normalization decisions. The UI must be able to explain outcomes such as "these paragraphs differ only in hyphenation" or "this passage was decoded with replacement characters."

Normalization is pure and side-effect free. It must not depend on wall-clock time, network state, random ordering, locale defaults, or mutable global caches. The same input bytes, upload metadata, parser version, and normalization options must always produce the same `Document`. This is a hard requirement for the golden-corpus tests in [Testing strategy](./13-testing-strategy.md).

Idempotence is part of the contract. Running normalization again over normalized block text must not keep changing whitespace, offsets, warnings, or block boundaries.

## What normalization deliberately does not do

Normalization does not perform:

- Spelling correction.
- Case folding by default.
- Stemming or lemmatization.
- Semantic rewriting.
- Translation.
- Expansion of abbreviations without source evidence.
- Modernization of archaic spelling.

`palimpsest` reports what the text says, not what it meant. A witness that reads `honour` and a witness that reads `honor` differ. A witness that reads `God` and one that reads `god` differ unless the researcher explicitly chooses comparison options that ignore case.

## Tokenization preview

After normalization, the diff engine tokenizes block text. In `Granularity.WORD`, a `WORD` token is a word plus its trailing whitespace. Keeping trailing whitespace attached to the token lets the unified and synoptic renderers preserve readable prose without inventing spacing after the diff.

This document stops at the ingestion boundary: canonical blocks and normalized text. Alignment, token status assignment, move detection, split and merge handling, and `DiffBlock` construction are specified in [Diff engine](./04-diff-engine.md).
