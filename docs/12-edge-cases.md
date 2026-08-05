This document catalogues real-world manuscript ingestion, normalization, alignment, and operational edge cases so implementations fail honestly and recoverably.

**Status:** Draft

**Related:** [Ingestion and parsers](./02-ingestion-and-parsers.md) · [Normalization](./03-normalization.md) · [Diff engine](./04-diff-engine.md) · [API reference](./06-api-reference.md) · [Session storage](./07-session-storage.md) · [Design system](./09-design-system.md) · [Testing strategy](./13-testing-strategy.md)

## Case format and warning policy

Each case states the symptom, why it happens, the detection rule, the handling policy, and whether ingestion emits an `IngestionWarning`. Warning codes are stored in `IngestionWarning.code`; non-recoverable failures instead use the RFC 9457 error `code` from [API reference](./06-api-reference.md).

`ARTIFACT` means `BlockKind.ARTIFACT`. `WORD` and `CHARACTER` mean `Granularity.WORD` and `Granularity.CHARACTER`. Manuscript A and Manuscript B are never described as left and right.

## Hyphenation

Hyphenation is the centre of normalization because three different marks are visually similar and semantically different.

| Mark | Example | Meaning | Default policy | Warning |
|---|---|---|---|---|
| Hard hyphen | `self-evident`, `well-being` | The hyphen belongs to the word. | Preserve it. | None unless a competing line-break decision was made. |
| Soft or discretionary hyphen | `unfor-\ntunate` | The hyphen was inserted by layout to justify a line. | Join to `unfortunate` only when evidence supports the join. | `DEHYPHENATION_DECISION` when changed. |
| Em dash or en dash | `Reader—do not mistake this.` | Punctuation, not word formation. | Preserve the dash and surrounding spacing. | None unless folded from an unusual code point. |

### Symptom

PDF extraction produces line-end hyphens that may be real compounds, soft breaks, or punctuation. The same source page can contain all three:

```text
It was self-
evident that the unfor-
tunate visitor—still wet from the rain—had not come for well-being alone.
```

The correct normalized prose is:

```text
It was self-evident that the unfortunate visitor—still wet from the rain—had not come for well-being alone.
```

### Why it happens

PDFs do not store paragraphs. They store positioned glyphs. A typesetter may add a discretionary hyphen at a line break, while a real compound such as `self-evident` may also break at the hyphen because the line happens to end there. Extraction sees both as `-\n`.

### Why the naive rule corrupts texts

The rule below is forbidden:

```python
re.sub(r'-\n(\w)', r'\1', text)
```

Applied to the hard compound:

```text
self-
evident
```

it produces:

```text
selfevident
```

That destroys a real lexical compound and creates a false textual variant. It also mishandles punctuation: `rain—\nstill` is not a word to be joined, and `word-\n—dash` is not a hyphenated token at all.

### Detection rule

For every candidate matching a line-final hyphen followed by a letter-like character, normalization evaluates both candidates:

| Candidate | Example from `self-\nevident` | Example from `unfor-\ntunate` |
|---|---|---|
| Joined | `selfevident` | `unfortunate` |
| Hyphen-preserved | `self-evident` | `unfor-tunate` |

The rule considers:

1. Lexicon evidence for both the joined and hyphen-preserved candidates.
2. Whether the hyphenated compound appears elsewhere in the same witness away from a line break; `self-evident` elsewhere is a strong signal to preserve `self-\nevident` as `self-evident`.
3. Language-aware behaviour from `DocumentMetadata.detected_language`. English often treats common compounds as lexical hyphenation; German compounds are more likely to be closed words, and a line-end hyphen inside a long German noun is more often discretionary.
4. Unicode dash class. `‐`, `‑`, `–`, and `—` are not treated as identical. En and em dashes are punctuation. Non-breaking hyphen is a hard-hyphen signal.
5. Local context. Capitalized second fragments, digits, initials, and prefixes such as `re-` are conservative cases.

### Handling policy

Normalization must be conservative and reversible:

- Join only when the joined candidate is lexicon-valid and the hyphen-preserved candidate is not, or when the language-specific rule gives the joined form higher confidence.
- Preserve the hyphen when the hyphenated compound appears elsewhere in the same witness.
- Preserve the hyphen when both candidates are plausible and the decision is uncertain.
- Record every join as a deterministic decision with source offsets so the UI can explain it and, if necessary, reconstruct the pre-normalized spelling.
- Emit `IngestionWarning` with `code="DEHYPHENATION_DECISION"` for every block where normalization removes a line-final hyphen to join a word. Preserving a hard hyphen while reflowing a line break is ordinary reflow, not dehyphenation; use `REFLOW_DECISION` only when the geometry-driven reflow itself is uncertain.

`dehyphen` is rejected. It is GPL-3.0, which is incompatible with this Apache-2.0 project, and it is stale, with Python 3.6-3.8 classifiers rather than Python 3.12+ support. The implementation must not depend on it.

### Worked table

| Input | Evidence | Correct output | Warning |
|---|---|---|---|
| `unfor-\ntunate` | `unfortunate` is lexicon-valid; `unfor-tunate` is not. | `unfortunate` | `DEHYPHENATION_DECISION` |
| `inter-\nnational` | `international` is lexicon-valid; `inter-national` is weak. | `international` | `DEHYPHENATION_DECISION` |
| `self-\nevident` | `self-evident` is lexicon-valid and appears elsewhere. | `self-evident` | None for preserving the hard hyphen; `REFLOW_DECISION` only if the line reflow is uncertain. |
| `well-\nbeing` | `well-being` is a common compound. | `well-being` | None if preserved. |
| `re-\nenter` | `re-enter` and `reenter` may both be valid by language and period. | Preserve source as `re-enter` unless configured evidence proves otherwise. | None if preserved. |
| `visitor—\nstill` | Em dash is punctuation. | `visitor—still` or `visitor— still` according to surrounding spacing normalization, never `visitorstill`. | None. |
| `mother-\nin-law` | Compound spans several hyphenated parts. | `mother-in-law` | None if preserved. |
| `Schiff-\nfahrt` | German compound; joined form may be expected. | `Schifffahrt` when language and lexicon evidence agree. | `DEHYPHENATION_DECISION` |

## PDF noise

### Soft line breaks inside paragraphs

**Symptom.** Extracted prose contains hard newlines inside one paragraph:

```text
It was the best of times, it was the worst
of times, it was the age of wisdom.
```

**Why it happens.** PDF text is laid out by visual line, not by paragraph.

**Detection rule.** Join adjacent lines when there is no blank line, no strong indentation change, no verse pattern, and the next line begins with a lowercase continuation or otherwise matches the same baseline and column geometry.

**Handling policy.** Reflow into one `PARAGRAPH` block:

```text
It was the best of times, it was the worst of times, it was the age of wisdom.
```

Never reflow `VERSE_LINE` blocks. Emit `IngestionWarning` with `code="REFLOW_DECISION"` when geometry is uncertain.

Verse is not merely exempted from reflow; it is segmented into one `VERSE_LINE` block per line, so that the line rather than the stanza becomes the unit of comparison. See [Normalization](./03-normalization.md), which also states why the heuristic is biased toward prose and what that bias rejects.

### Running heads and folio numbers

**Symptom.** Every page contributes noise such as `MIDDLEMARCH` or `127`.

**Why it happens.** Running heads, footers, and folio numbers are real text on the page but not part of the witness prose.

**Detection rule.** A short span recurring across pages in the same top or bottom band, with stable horizontal alignment, is classified as `ARTIFACT`. Bare arabic or roman numerals near the outer lower margin are folio candidates.

**Handling policy.** Preserve them as `BlockKind.ARTIFACT` blocks, exclude them from diffing by default, and surface them as collapsible evidence. Emit `IngestionWarning` with `code="ARTIFACT_CLASSIFIED"` when a repeated-position heuristic classifies content.

### Footnotes and marginalia colliding with body text

**Symptom.** A sentence reads:

```text
The king departed at dawn. 1 This reading is doubtful through the eastern gate.
```

**Why it happens.** Positional extraction may interleave footnotes, marginalia, and body text by content-stream order or by naive vertical sorting.

**Detection rule.** Text in smaller font-size bands, lower page bands, side margins, superscript-leading fragments, or blocks disconnected from the main column is suspected note material.

**Handling policy.** Prefer preserving main-flow body text and emit note-like material as separate `ARTIFACT` blocks when geometry is clear. If geometry is not clear, keep the extracted order and emit `IngestionWarning` with `code="READING_ORDER_UNCERTAIN"`; do not silently invent a body order.

### Multi-column layouts

**Symptom.** Extracted text alternates between columns:

```text
First column sentence Second column sentence continues first column continues second column
```

**Why it happens.** The content stream or extraction engine returns glyphs in drawing order rather than reading order.

**Detection rule.** Page geometry shows two or more stable x-ranges with overlapping y-ranges and comparable line heights.

**Handling policy.** `PdfPlumberParser` reads column bands top-to-bottom within each column when geometry is unambiguous. If interleaving cannot be resolved, return the best extractable text with `IngestionWarning` code `MULTICOLUMN_UNCERTAIN`. This is an honest v1 quality ceiling; the UI must not pretend the collation is authoritative.

### Tables and figure captions

**Symptom.** A table becomes prose fragments such as `Year 1851 1852 Sales 10 12` or captions interrupt body text.

**Why it happens.** Table cells and captions are positioned glyphs without a document-level semantic model.

**Detection rule.** Repeated x-alignments, dense ruled regions, tabular whitespace, caption prefixes such as `Figure 2.`, and blocks near images indicate non-prose content.

**Handling policy.** Flatten small tables and captions into `ARTIFACT` unless the parser can produce coherent `PARAGRAPH` text. Emit `IngestionWarning` with `code="NON_PROSE_FLATTENED"`.

### Drop caps and small caps splitting the first word

**Symptom.** A chapter begins `T HE evening was calm.` or `H e entered the room.`

**Why it happens.** Decorative capitals and small caps are separate positioned glyph runs with different fonts and baselines.

**Detection rule.** At the start of a `PARAGRAPH`, a single large glyph or small-cap run abuts the following lowercase or small-cap letters with no real word gap.

**Handling policy.** Recombine only at block start when geometry and spacing support a single word: `THE evening was calm.` or `He entered the room.` Emit `IngestionWarning` with `code="DROP_CAP_RECOMBINED"`.

### Ligatures

**Symptom.** Text contains `ﬁ`, `ﬂ`, or `ﬀ`: `The ﬁrst ﬂower fell.`

**Why it happens.** Fonts substitute ligature glyphs, and extraction may return the compatibility character rather than the component letters.

**Detection rule.** Unicode ligature code points in normalized text.

**Handling policy.** Fold common Latin ligatures to letters for comparison and display text: `The first flower fell.` Emit `IngestionWarning` with `code="LIGATURE_FOLDED"` when folding occurs.

### Embedded-font mojibake

**Symptom.** Extracted text reads `7KH TXHHQ` or `Ã¢â‚¬Å“` where the page visibly contains normal prose.

**Why it happens.** A PDF may have broken or custom encoding maps from glyph ids to Unicode.

**Detection rule.** High replacement-character rates, impossible character distributions for the detected language, repeated private-use code points, or classic mojibake sequences.

**Handling policy.** If a deterministic repair is available, repair and emit `IngestionWarning` code `ENCODING_REPAIRED`. Otherwise return `MALFORMED_DOCUMENT` when the witness cannot be read as text, or emit `IngestionWarning` code `ENCODING_UNCERTAIN` for partial extraction.

### Page break mid-sentence and mid-word

**Symptom.** Page boundaries interrupt prose:

```text
He crossed the thresh-
[page break]
old without speaking.
```

**Why it happens.** Page-local extraction reports each page separately.

**Detection rule.** End-of-page line lacks terminal punctuation and the next page begins with a lowercase continuation, or a dehyphenation candidate spans the page boundary.

**Handling policy.** Reflow across pages when the same column geometry and block continuation evidence are present. Preserve `Block.page` as the starting page. Emit `IngestionWarning` with `code="PAGE_BREAK_REFLOW"`.

### PDFs with no extractable text

**Symptom.** A visible scanned page yields no text.

**Why it happens.** The PDF contains images rather than embedded text.

**Detection rule.** Sampled pages have a median of fewer than 20 non-whitespace characters after extraction.

**Handling policy.** Do not create an empty `Document`. Return RFC 9457 error `code="OCR_REQUIRED"`, which is the v1 hand-off to `AsyncOCRParser` and `SourceFormat.OCR`. No `IngestionWarning` is emitted because no `Document` exists.

## DOCX cases

### Tracked changes

**Symptom.** The package contains insertions and deletions from Word revision tracking.

**Why it happens.** `python-docx` reads the resolved main document body and does not expose a scholarly apparatus of revisions.

**Detection rule.** WordprocessingML contains revision elements such as inserted or deleted runs.

**Handling policy.** v1 warns and uses only the resolved body text exposed by `DocxParser`; it must not silently accept either the original or revised text without saying which. Emit `IngestionWarning` with `code="TRACKED_CHANGES_IGNORED"`.

### Comments and footnotes outside the body

**Symptom.** A scholar expects a footnote or comment to appear, but no `Block` contains it.

**Why it happens.** Comments, footnotes, endnotes, headers, and footers live outside the main document body.

**Detection rule.** The DOCX package contains comments, footnotes, endnotes, header, or footer parts.

**Handling policy.** Do not include them in body `blocks` in v1. Emit `IngestionWarning` with `code="NON_BODY_TEXT_IGNORED"`.

### Text boxes and floating frames

**Symptom.** Pull quotes or boxed prose disappear or appear out of order.

**Why it happens.** Floating shapes are stored outside the normal paragraph sequence.

**Detection rule.** Drawing, shape, textbox, or frame elements contain textual runs.

**Handling policy.** Exclude from body `blocks` unless a deterministic document-order extraction exists. Emit `IngestionWarning` with `code="FLOATING_TEXT_IGNORED"`.

### Nested tables

**Symptom.** Prose in nested tables flattens into an unnatural sequence.

**Why it happens.** The v1 block model has no table-cell hierarchy.

**Detection rule.** Table elements contain child tables or mixed paragraphs and tables.

**Handling policy.** Flatten in deterministic row-major order only when text remains readable; otherwise classify as lossy and emit `IngestionWarning` code `NESTED_TABLE_FLATTENED`.

### Localized or renamed heading styles

**Symptom.** A Spanish `Título 1` paragraph is returned as `PARAGRAPH` rather than `HEADING`.

**Why it happens.** Naive matching against literal style names such as `Heading 1` misses localized or renamed styles.

**Detection rule.** Inspect style metadata where available and maintain known localized aliases; fall back to the original `Block.style` value.

**Handling policy.** Recognize built-in heading styles by stable style id when available. If only a localized style name is available and not recognized, preserve `Block.style`, classify conservatively as `PARAGRAPH`, and emit `IngestionWarning` code `STYLE_MAPPING_UNCERTAIN`.

## Plain text and Markdown cases

### UTF-16 and legacy encodings masquerading as `.txt`

**Symptom.** Plain text begins with visible nulls or replacement characters.

**Why it happens.** The extension says text, but bytes may be UTF-16, Windows-1252, or another legacy encoding.

**Detection rule.** BOM detection first, then UTF-8, then deterministic fallback with replacement tracking.

**Handling policy.** Honor UTF-8, UTF-16 LE, and UTF-16 BE BOMs. For fallback decoding, emit `IngestionWarning` with `code="ENCODING_UNCERTAIN"`.

### BOM handling

**Symptom.** The first block begins with `\ufeff`.

**Why it happens.** The Unicode BOM was decoded as content.

**Detection rule.** Leading BOM code point after decoding.

**Handling policy.** Strip the leading BOM before block segmentation. Emit no warning unless conflicting BOM and byte evidence require fallback, in which case use `ENCODING_UNCERTAIN`.

### Mixed line endings

**Symptom.** The same witness contains `\r\n`, `\n`, and `\r`.

**Why it happens.** Text was edited or exported through multiple systems.

**Detection rule.** More than one line-ending convention appears in decoded text.

**Handling policy.** Normalize to `\n` before segmentation. Emit `IngestionWarning` code `MIXED_LINE_ENDINGS` only when the mixture changes block boundaries.

### Windows-1252 smart quotes decoded as mojibake

**Symptom.** `He said, Ã¢â‚¬Å“Come in.Ã¢â‚¬Â`

**Why it happens.** UTF-8 bytes were interpreted as Windows-1252 or the reverse.

**Detection rule.** Recognize common mojibake sequences and high replacement-character density.

**Handling policy.** Apply only deterministic repairs; otherwise preserve the decoded text and warn with `ENCODING_UNCERTAIN`. Never silently rewrite ambiguous scholarly characters.

### Extremely long single-line witnesses

**Symptom.** A 100,000-token witness appears as one `PARAGRAPH` block.

**Why it happens.** Plain text export lost paragraph breaks.

**Detection rule.** One line or block exceeds the configured block budget while containing sentence punctuation and no blank lines.

**Handling policy.** Segment conservatively at sentence boundaries only when necessary to protect diff budgets; emit `IngestionWarning` code `LONG_LINE_SEGMENTED`. If budgets still fail, return `DIFF_BUDGET_EXCEEDED` during comparison.

### Markdown inline formatting polluting the diff

**Symptom.** `*dark*` differs from `dark` only because of asterisks.

**Why it happens.** Markdown markup is not witness prose.

**Detection rule.** Inline emphasis, strong, code, link, and image syntax inside Markdown paragraphs.

**Handling policy.** Strip inline formatting for prose comparison while preserving visible label text. Emit `IngestionWarning` code `MARKDOWN_INLINE_STRIPPED` when syntax is discarded.

## Text and script cases

### Right-to-left scripts and bidirectional runs

**Symptom.** Hebrew or Arabic text appears visually reordered, and UI labels describe panes as left and right.

**Why it happens.** Logical storage order, visual rendering order, and pane placement diverge under bidirectional text.

**Detection rule.** Strong RTL code points or bidirectional isolates in a block.

**Handling policy.** Preserve logical Unicode order, set direction per block in the UI, and always say Manuscript A and Manuscript B. Emit `IngestionWarning` code `BIDI_TEXT_DETECTED` only when mixed-direction runs may affect reading order.

### CJK text and `WORD` tokenization

**Symptom.** Chinese or Japanese prose becomes one enormous token because there are no spaces.

**Why it happens.** `Granularity.WORD` assumes space-separated tokens.

**Detection rule.** High proportion of CJK code points and low whitespace density.

**Handling policy.** v1 does not implement language-specific segmentation. Fall back to `Granularity.CHARACTER` for comparison when `WORD` would create pathological tokens, and surface the choice in `ComparisonResult.options`. Emit `IngestionWarning` with `code="CHARACTER_GRANULARITY_FALLBACK"`.

### Combining diacritics and NFC normalization

**Symptom.** `é` and `e\u0301` appear identical but compare as different code point sequences.

**Why it happens.** Unicode allows precomposed and decomposed spellings.

**Detection rule.** Text contains combining marks or non-NFC sequences.

**Handling policy.** Normalize to NFC because it preserves the character while stabilizing representation. Emit no warning for routine NFC normalization; warn with `UNICODE_NORMALIZED` only when offsets or block text explanation requires it.

### Zero-width and non-breaking spaces

**Symptom.** Words do not wrap, or invisible characters create unexpected token boundaries.

**Why it happens.** Exporters insert `\u200b`, `\u2060`, or `\u00a0` for layout.

**Detection rule.** Presence of zero-width or non-breaking spacing code points.

**Handling policy.** Fold non-breaking spaces to ordinary spaces for comparison while preserving token text where display requires it; remove zero-width layout controls only when they are not part of a script-specific shaping requirement. Emit `IngestionWarning` code `INVISIBLE_SPACE_NORMALIZED`.

### Greek and Cyrillic homoglyphs

**Symptom.** `A` and Cyrillic `А`, or Greek `ο` and Latin `o`, look identical but differ.

**Why it happens.** Different scripts contain visually similar code points.

**Detection rule.** Mixed-script confusables inside one token or adjacent tokens.

**Handling policy.** Do not normalize away homoglyphs silently. For a textual scholar, script substitution can be a real finding. Preserve the code points and emit `IngestionWarning` code `HOMOGLYPH_CONFUSABLE` so the UI can call attention to them.

## Diff and alignment pathologies

### Completely unrelated witnesses

**Symptom.** Manuscript A is `Pride and Prejudice`; Manuscript B is `Moby-Dick`.

**Why it happens.** The wrong witnesses were uploaded or titles were confused.

**Detection rule.** Document `DiffMetrics.similarity` is near zero and almost no blocks clear `align_threshold=0.50`.

**Handling policy.** Return a useless-but-honest `ComparisonResult`: mostly `DELETED` blocks from Manuscript A and `INSERTED` blocks from Manuscript B, low similarity, and no fabricated matches. No `IngestionWarning` is emitted because ingestion succeeded.

### A witness compared against itself

**Symptom.** Every block is `UNCHANGED` and `DiffMetrics.similarity` is `1.0`.

**Why it happens.** The same `document_id` or duplicate upload was used for Manuscript A and Manuscript B.

**Detection rule.** Identical document ids or identical content hashes.

**Handling policy.** Return a valid `ComparisonResult` with zero edits. The UI may state that the witnesses are identical. No warning.

### Empty or whitespace-only witnesses

**Symptom.** Parsing succeeds but no diffable `Block` values exist.

**Why it happens.** The source contained only whitespace, artifacts, or non-extractable text.

**Detection rule.** After normalization, there are no non-`ARTIFACT` blocks with non-whitespace text.

**Handling policy.** Return RFC 9457 error `code="EMPTY_DOCUMENT"`. No `IngestionWarning` is emitted because no useful `Document` exists.

### One witness vastly longer

**Symptom.** Manuscript B is an entire novel and Manuscript A is one chapter.

**Why it happens.** A partial witness was compared to a full witness.

**Detection rule.** `a_word_count` and `b_word_count` differ by a large ratio and anchors cover only one region.

**Handling policy.** Produce the honest structural result: the common region aligns, and the unmatched range is `INSERTED` or `DELETED`. If absolute budgets are exceeded, return `DIFF_BUDGET_EXCEEDED`.

### Repetitive refrains, litanies, and boilerplate

**Symptom.** Repeated lines such as `And his mercy endureth for ever.` are reported as many `MOVED` blocks.

**Why it happens.** Many blocks score above `move_threshold=0.75`, and the LIS may choose the wrong occurrence.

**Detection rule.** High duplicate-block frequency and several candidate pairs within a small score band.

**Handling policy.** This is the known quality ceiling of move detection. Keep `move_threshold=0.75`, expose `?moves=off`, and never hide the raw `DiffBlock` metrics. No ingestion warning; the concern belongs to alignment.

### A paragraph both moved and heavily edited

**Symptom.** A block changes position and many tokens change.

**Why it happens.** The author relocated and revised the passage.

**Detection rule.** A matched pair is outside the LIS and clears `move_threshold=0.75`, but `BlockMetrics.churn` is high.

**Handling policy.** Emit `BlockStatus.MOVED`; structural status dominates. `BlockMetrics` still reports `edit_count`, `insertions`, `deletions`, and `churn` so the edit is visible.

### Whitespace-only differences

**Symptom.** One witness has doubled spaces or hard line wraps only.

**Why it happens.** Export, OCR, or formatting changed whitespace.

**Detection rule.** With `DiffOptions.normalize_whitespace=True`, comparison keys match while surface token spacing differs.

**Handling policy.** Treat as unchanged by default, while preserving the normalized text. If `normalize_whitespace=False`, show the differences. No warning unless normalization was uncertain.

### Pure re-paragraphing

**Symptom.** One paragraph becomes two paragraphs without changing any words.

**Why it happens.** Editorial paragraphing changed.

**Detection rule.** Split or merge concatenation clears `align_threshold=0.50`, and token reconstruction shows no `INSERTION` or `DELETION` tokens.

**Handling policy.** Emit `BlockStatus.SPLIT` or `BlockStatus.MERGED`, shared `group_id`, zero token edits, and structural metrics. This must read as a structural change, not as a rewrite.

## Untrusted input

The first thing this application does is accept a file from someone it knows
nothing about. Every limit below exists because a file can be built to cost
more than it appears to, and because the size of an upload says almost nothing
about the work it demands.

These are configuration, not promises. They are the numbers this deployment is
willing to spend, and a different deployment may set them differently through
the `PALIMPSEST_` environment prefix.

### Decompression bombs

**Symptom.** A small `.docx` exhausts memory and takes the process down.

**Why it happens.** A `.docx` is a ZIP. The upload cap counts *compressed*
bytes, and a ZIP built for the purpose expands by three orders of magnitude. A
120 KiB archive of one repeated byte expands to 120 MiB; at that ratio a 25 MiB
upload that passes the cap becomes about 25 GiB.

**Detection rule.** Sum the declared uncompressed sizes from the archive's
central directory and compare against `max_decompressed_bytes`. Nothing is
decompressed to do this, so an honest manuscript pays nothing.

**Handling policy.** Refuse with `code="FILE_TOO_LARGE"` (`413`), naming both
the declared size and the limit. The file is well formed; it is simply more
than this deployment will spend, which is a different answer from "malformed"
and deserves a different one.

**Why the declared size can be trusted here.** It is written by whoever built
the archive, which looks like exactly the wrong thing to trust. It is safe
against this reader: `zipfile` stops a member at its declared length and then
fails the CRC, so an archive holding 8 MiB while declaring 1 KiB delivers zero
bytes and raises `BadZipFile`. python-docx reads through the same library. A
streaming counter was written to defend against under-declaration and then
removed once this was tested rather than assumed — it would have decompressed
every legitimate upload in full to prevent something the library already
prevents. The behaviour is pinned by a test so that a future Python which
changes it fails loudly.

### Page-count bombs

**Symptom.** A small PDF takes a very long time to ingest.

**Why it happens.** A PDF states its own page count and every page is then
examined for text and geometry. Page objects are cheap and shareable, so the
work a request costs is set by the file's structure rather than by its size.

**Detection rule.** Compare the declared page count against `max_pdf_pages`
before the first page is touched.

**Handling policy.** Refuse with `code="FILE_TOO_LARGE"`, naming the count and
the limit.

### What is not bounded

Stated plainly, because a limit nobody wrote down is indistinguishable from one
nobody thought of:

| Not bounded | Why it is acceptable for now |
|---|---|
| Time spent parsing one accepted file | The size and page limits bound the input, and the diff engine has its own token and block ceilings. No wall-clock budget exists; a pathological file within all limits could still be slow. |
| Concurrent expensive requests | Rate limiting bounds request *count* per client, not total work in flight. A deployment expecting hostile load needs a process manager with memory limits, not only these numbers. |
| Nested archives | A `.docx` member is never itself unpacked, so there is no recursion to bound. This holds only while no parser unpacks a member. |

### Limits

| Setting | Default | Bounds |
|---|---:|---|
| `max_upload_bytes` | 25 MiB | Bytes accepted from the network |
| `max_decompressed_bytes` | 128 MiB | What one upload may become once unpacked |
| `max_pdf_pages` | 5,000 | Pages one document may declare |

The decompression and page ceilings sit well above any manuscript this tool
will collate — the token ceiling puts a full-length book at a few megabytes of
text and a few hundred pages — and far below anything that threatens the
process. Refusing a real manuscript is the expensive failure, so the headroom
is deliberate.

## Operational cases

### Upload size limits

**Symptom.** The upload exceeds 25 MiB per witness.

**Why it happens.** Manuscripts can include images, embedded fonts, or scans.

**Detection rule.** Middleware checks `Content-Length` and counts streamed bytes.

**Handling policy.** Return RFC 9457 error `code="FILE_TOO_LARGE"` as soon as the limit is known.

### `Content-Length` lying

**Symptom.** A request declares 10 MiB but streams more than 25 MiB.

**Why it happens.** Clients can send incorrect or malicious headers.

**Detection rule.** Count bytes while streaming, not just at the header.

**Handling policy.** Abort parsing and return `FILE_TOO_LARGE`. Do not write partial witness content.

### Expired comparisons

**Symptom.** `/api/v1/comparisons/{comparison_id}` once worked and now returns an error.

**Why it happens.** `comparisons.expires_at` passed.

**Detection rule.** Read path checks `expires_at` before returning content.

**Handling policy.** Return `COMPARISON_EXPIRED` for expired-but-known comparisons, or `COMPARISON_NOT_FOUND` if already swept and indistinguishable from an unknown id.

### A document expiring before a comparison that references it

**Symptom.** The comparison row exists, but Manuscript A or Manuscript B has expired.

**Why it happens.** Documents and comparisons have independent TTLs and the sweeper may run between reads.

**Detection rule.** Comparison read validates referenced `documents` rows and their `expires_at` values.

**Handling policy.** Return `COMPARISON_EXPIRED`; foreign-key cascade handles swept rows.

### Duplicate uploads of an identical witness

**Symptom.** The same source is uploaded twice and receives two ids.

**Why it happens.** v1 has TTL session storage, not accounts or a content library.

**Detection rule.** Content hash and normalized `Document` hash match an unexpired row.

**Handling policy.** The API may return the existing `DocumentSummary` or create another unguessable id, but comparison against identical content must produce `DiffMetrics.similarity=1.0` and only `UNCHANGED` blocks. No warning.

## Triage table

| Case | Detection | Policy | Warning or error code |
|---|---|---|---|
| Soft hyphenation | Line-final hyphen plus letter-like continuation | Lexicon, document-local compound, language-aware reversible decision | `DEHYPHENATION_DECISION` |
| Hard hyphenated compound | Hyphen-preserved candidate valid or repeated elsewhere | Preserve hard hyphen | None |
| Em/en dash punctuation | Unicode dash punctuation at break | Preserve punctuation | None |
| Soft line breaks | Same paragraph geometry and continuation evidence | Reflow prose, never verse | `REFLOW_DECISION` |
| Verse | Three or more lines of consistent short measure, each a phrase | Segment into one `VERSE_LINE` block per line | `VERSE_SEGMENTED` |
| Running heads and folio numbers | Repeated text at repeated page position | Emit `ARTIFACT` and exclude by default | `ARTIFACT_CLASSIFIED` |
| Footnotes and marginalia collision | Note-sized or margin-positioned text interleaves with body | Separate as `ARTIFACT` when clear; otherwise keep and warn | `READING_ORDER_UNCERTAIN` |
| Decompression bomb | Declared uncompressed total over `max_decompressed_bytes` | Refuse before decompressing | `FILE_TOO_LARGE` |
| Page-count bomb | Declared page count over `max_pdf_pages` | Refuse before reading the first page | `FILE_TOO_LARGE` |
| Multi-column PDF | Stable overlapping column bands | Resolve clear columns; otherwise honest uncertain extraction | `MULTICOLUMN_UNCERTAIN` |
| Tables and captions | Tabular x-alignments or caption prefixes | Flatten or classify as `ARTIFACT` | `NON_PROSE_FLATTENED` |
| Drop caps and small caps | Decorative first glyph split from word | Recombine only with geometry evidence | `DROP_CAP_RECOMBINED` |
| Ligatures | Unicode ligature code points | Fold common Latin ligatures | `LIGATURE_FOLDED` |
| Embedded-font mojibake | Replacement characters, private-use glyphs, impossible distributions | Repair deterministically or fail | `ENCODING_REPAIRED`, `ENCODING_UNCERTAIN`, or `MALFORMED_DOCUMENT` |
| Page break mid-sentence or mid-word | End-page continuation evidence | Reflow across pages | `PAGE_BREAK_REFLOW` |
| Scanned PDF | Median sampled page below text threshold | Return OCR hand-off error | `OCR_REQUIRED` |
| DOCX tracked changes | Revision XML elements | Use resolved body text and warn | `TRACKED_CHANGES_IGNORED` |
| DOCX comments and footnotes | Non-body package parts | Exclude from body `blocks` | `NON_BODY_TEXT_IGNORED` |
| DOCX text boxes and frames | Floating shape text | Exclude unless deterministic | `FLOATING_TEXT_IGNORED` |
| DOCX nested tables | Child tables or mixed hierarchy | Flatten row-major when readable | `NESTED_TABLE_FLATTENED` |
| Localized heading styles | Unknown style name or id | Preserve `Block.style`, classify conservatively | `STYLE_MAPPING_UNCERTAIN` |
| UTF-16 or legacy text | BOM, failed UTF-8, fallback decode | Decode deterministically | `ENCODING_UNCERTAIN` |
| BOM | Leading BOM | Strip before segmentation | None |
| Mixed line endings | Multiple line-ending conventions | Normalize to `\n` | `MIXED_LINE_ENDINGS` |
| Windows-1252 mojibake | Classic mojibake sequences | Repair only if deterministic | `ENCODING_UNCERTAIN` |
| Extremely long line | Huge block without breaks | Segment conservatively or fail budget | `LONG_LINE_SEGMENTED` or `DIFF_BUDGET_EXCEEDED` |
| Markdown inline formatting | Markdown inline syntax | Strip markup, preserve label text | `MARKDOWN_INLINE_STRIPPED` |
| RTL and bidirectional text | Strong RTL or mixed bidi runs | Preserve logical order; label Manuscript A/B | `BIDI_TEXT_DETECTED` |
| CJK without spaces | High CJK, low whitespace | Fall back to `CHARACTER` | `CHARACTER_GRANULARITY_FALLBACK` |
| Combining diacritics | Non-NFC sequences | Normalize to NFC | `UNICODE_NORMALIZED` when surfaced |
| Zero-width and non-breaking spaces | Invisible spacing code points | Normalize layout spaces conservatively | `INVISIBLE_SPACE_NORMALIZED` |
| Greek and Cyrillic homoglyphs | Mixed-script confusables | Preserve and surface as scholarly evidence | `HOMOGLYPH_CONFUSABLE` |
| Unrelated witnesses | Near-zero similarity | Honest mostly `DELETED` and `INSERTED` result | None |
| Witness compared with itself | Same id or content hash | Valid all-`UNCHANGED` result | None |
| Empty witness | No diffable non-`ARTIFACT` blocks | Reject upload | `EMPTY_DOCUMENT` |
| Vast length mismatch | Large word-count ratio | Align common region, mark rest structural | `DIFF_BUDGET_EXCEEDED` if over budget |
| Repetitive text move false positives | Many near-tie duplicate candidates | Keep threshold; expose `?moves=off` | None |
| Moved and edited block | Outside LIS and high churn | `MOVED` plus token metrics | None |
| Whitespace-only differences | Comparison keys match after whitespace normalization | Treat unchanged by default | None |
| Pure re-paragraphing | Split/merge with zero token edits | Structural `SPLIT` or `MERGED`, not rewrite | None |
| Upload too large | Header or stream exceeds 25 MiB | Reject request | `FILE_TOO_LARGE` |
| Lying `Content-Length` | Stream count exceeds declared limit | Abort and reject | `FILE_TOO_LARGE` |
| Expired comparison | `comparisons.expires_at` passed | Reject read | `COMPARISON_EXPIRED` or `COMPARISON_NOT_FOUND` |
| Expired referenced document | Source document missing or expired | Reject comparison read | `COMPARISON_EXPIRED` |
| Duplicate upload | Content hash match | Reuse or duplicate id; identical comparison is unchanged | None |
