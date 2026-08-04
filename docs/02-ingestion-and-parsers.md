This document specifies how uploaded witnesses become canonical `Document` objects, including parser selection, concrete parser behaviour, and the OCR extension seam.

**Status:** Draft

**Related:** [Specification index](./README.md) · [Architecture](./01-architecture.md) · [Normalization](./03-normalization.md) · [Edge cases](./12-edge-cases.md) · [Testing strategy](./13-testing-strategy.md)

## Load-bearing invariant

Ingestion is the only layer that knows about source formats. `backend/app/services/ingestion/{base,registry,plaintext,markdown,docx,pdf_plumber,pdf_pypdf,normalize}.py` accepts a witness as bytes plus upload metadata and returns a canonical `Document`. Everything downstream, including `backend/app/services/diffing/{engine,alignment,tokenizer,metrics,moves}.py` and `backend/app/services/formatting/{payload,unified,synoptic}.py`, sees only `Document`, `Block`, `DocumentMetadata`, `IngestionWarning`, and `BoundingBox`.

That invariant is what makes OCR a drop-in extension. A future OCR parser may be asynchronous, lossy, and confidence-bearing, but it still returns the same `Document` shape.

The seam is already present in the v1 schema rather than postponed to a migration: `Block.confidence`, `Block.bbox`, `DocumentMetadata.ocr_confidence`, `ParserCapabilities.is_async`, `ParserCapabilities.requires_network`, `ParserCapabilities.emits_confidence`, `ParserCapabilities.emits_bboxes`, and `SourceFormat.OCR` all exist before any OCR implementation ships. Adding `AsyncOCRParser` therefore changes parser selection and orchestration only; the diffing, formatting, storage payload, and frontend rendering contracts continue to consume `Document`.

## The parser contract

Every parser must implement `BaseDocumentParser` exactly. The registry resolves a `SourceProbe` to a parser class; the API layer instantiates that parser and calls the sync or async path selected by `ParserCapabilities.is_async`.

```python
from abc import ABC, abstractmethod
from typing import ClassVar


class BaseDocumentParser(ABC):
    """Base contract for all parsers that turn one uploaded witness into a Document."""

    name: ClassVar[str]
    version: ClassVar[str]
    supported_extensions: ClassVar[frozenset[str]]
    supported_media_types: ClassVar[frozenset[str]]

    @classmethod
    @abstractmethod
    def capabilities(cls) -> ParserCapabilities:
        """Return the static capabilities of this parser.

        Implementations must return the same ParserCapabilities for the same parser class
        across the life of the process. The registry and API layer use this value to choose
        the execution path, to warn researchers about lossy extraction, and to expose parser
        support through /api/v1/capabilities.
        """
        ...

    @classmethod
    @abstractmethod
    def can_parse(cls, probe: SourceProbe) -> bool:
        """Return whether this parser can parse the probed source.

        Implementations must decide from SourceProbe(filename, media_type, magic_bytes,
        size_bytes) only. They must not consume DocumentSource.stream, perform network I/O,
        or do expensive full-document parsing here. A True result means parse() or
        parse_async() is expected to either return a Document or raise a format-specific
        ingestion error, not silently delegate to another parser.
        """
        ...

    @abstractmethod
    def parse(self, source: DocumentSource) -> Document:
        """Parse the source witness and return a canonical Document.

        Implementations must return Document(id, title, source_format, blocks, metadata,
        warnings) with snake_case fields exactly as defined in the shared models. They are
        responsible for invoking the shared normalization stage so the returned Document
        has stable Block.id values within the document, assigned BlockKind values,
        char_start and char_end offsets into the reconstructed full text, and recoverable
        extraction issues surfaced as IngestionWarning entries. They must not return
        partially parsed empty documents for unsupported, malformed, or scanned sources;
        those are errors.
        """
        ...
```

### `ParserCapabilities`

| Field | Meaning | Why it exists |
|---|---|---|
| `preserves_headings` | The parser can reliably distinguish headings from paragraphs. | The UI and diffing stage can preserve a manuscript's visible structure instead of flattening every block to `PARAGRAPH`. |
| `preserves_page_numbers` | The parser can attach page provenance to `Block.page`. | Page numbers support citation, source mapping, and PDF noise heuristics. |
| `is_lossy` | The parser may lose layout, order, typography, or non-main-body material. | `is_lossy=True` drives a UI warning so researchers know the witness was reconstructed rather than read as clean prose. |
| `is_async` | The parser must be awaited through `parse_async`. | The API layer uses this flag to select the execution path and to avoid blocking a worker on OCR or network-bound parsing. |
| `requires_network` | The parser depends on a network service. | Air-gapped research environments can refuse such parsers by configuration before upload handling begins. |
| `emits_confidence` | The parser may populate `Block.confidence` and `DocumentMetadata.ocr_confidence`. | Reserved for OCR, where extraction certainty is part of the scholarly evidence. |
| `emits_bboxes` | The parser may populate `Block.bbox`. | Reserved for OCR and positional extraction that can map text back to image or page coordinates. |

## Format detection

Extension sniffing alone is insufficient. Researchers rename witnesses while transcribing or exporting; a `.txt` upload may be UTF-16 text, Markdown, or a renamed `.docx`; a `.pdf` upload may be text-bearing or a page-image scan. The ingestion layer must therefore build a `SourceProbe(filename, media_type, magic_bytes, size_bytes)` from three signals.

| Signal | Examples | Use |
|---|---|---|
| Declared media type | `text/plain`, `text/markdown`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/pdf` | Strong when supplied by the browser or client, but not trusted alone. |
| File extension | `.txt`, `.md`, `.markdown`, `.docx`, `.pdf` | Useful for researcher intent and for plain text versus Markdown hints. |
| Magic bytes | `PK\x03\x04` for a ZIP container that may be `.docx`, `%PDF-` for PDF, UTF-8 BOM `\xef\xbb\xbf`, UTF-16 LE BOM `\xff\xfe`, UTF-16 BE BOM `\xfe\xff` | The most reliable signal for container and encoding families. A ZIP signature alone is not proof of DOCX; `DocxParser.can_parse` must also verify WordprocessingML parts such as `[Content_Types].xml` and `word/document.xml`. |

`ParserRegistry.resolve(probe) -> type[BaseDocumentParser]` must apply these precedence rules:

1. If the caller explicitly forces a parser by `BaseDocumentParser.name`, resolve that parser only after verifying `can_parse(probe)` is true. If it cannot parse the probe, return an `UNSUPPORTED_FORMAT` problem rather than falling back silently.
2. Prefer magic-byte matches over declared media type and extension. A source starting with `%PDF-` is treated as `SourceFormat.PDF` even if the filename ends in `.txt`.
3. Use declared media type next when it is specific and compatible with the magic bytes.
4. Use file extension as a tie-breaker and as the main signal for text-like formats without distinctive magic bytes.
5. If exactly one parser matches, return it.
6. If multiple parsers match, select the highest-priority parser in the explicit registration list.
7. If no parser matches, return an RFC 9457 `application/problem+json` error with `code` set to `UNSUPPORTED_FORMAT`.
8. If signals are ambiguous in a way that could change extracted text, return `UNSUPPORTED_FORMAT` with a detail string naming the conflicting signals.

A renamed `.docx` illustrates the rule:

```text
filename: witness.txt
media_type: text/plain
magic_bytes: PK\x03\x04...

resolution: DocxParser, because the ZIP container signature plus WordprocessingML parts outrank extension and media type.
```

## The registry

Parsers register through an explicit list in `backend/app/services/ingestion/registry.py`. Registration must not happen through import-time magic, entry-point scanning, or implicit subclass discovery. Explicit registration gives predictable startup, deterministic capabilities output, and no hidden plugin scan in deployments where file-system access is restricted.

The list order is also the priority order for ambiguous matches. PDF is the important case:

| Priority | Parser | Reason |
|---|---|---|
| 1 | `PdfPlumberParser` | Default PDF parser because it uses character-level positional data and supports layout-aware reconstruction. |
| 2 | `PyPdfParser` | Fast path and fallback when positional fidelity is not required or when `PdfPlumberParser` is unavailable by configuration. |

A caller can force a parser by name for diagnostics, reproducibility, or an administrative fallback. Forced selection is still bounded by `can_parse(probe)`; forcing `PyPdfParser` for a `DOCX` source returns `UNSUPPORTED_FORMAT`.

## Concrete parsers

### `PlainTextParser`

| Field | Value |
|---|---|
| Library | Python 3.12+ standard library |
| `source_format` | `SourceFormat.TXT` |
| `ParserCapabilities` | `preserves_headings=False`, `preserves_page_numbers=False`, `is_lossy=False`, `is_async=False`, `requires_network=False`, `emits_confidence=False`, `emits_bboxes=False` |

`PlainTextParser` decodes bytes, normalizes text enough to produce blocks, and emits `PARAGRAPH` blocks segmented by blank lines. It does not infer heading structure, because plain text conventions are too inconsistent to make that safe.

Encoding resolution is ordered:

1. Detect BOM: UTF-8 BOM `\xef\xbb\xbf`, UTF-16 LE BOM `\xff\xfe`, or UTF-16 BE BOM `\xfe\xff`.
2. Decode as UTF-8 if no BOM is present.
3. If UTF-8 fails, decode as UTF-8 with `errors="replace"` and emit an `IngestionWarning` explaining that replacement characters may appear.

The parser does not guess legacy encodings from byte frequency. Without a BOM or an explicit future encoding option, such guesses are not reproducible enough for golden-corpus tests.

Worked example:

```text
The title

It was the best of times.
It was the worst of times.
```

returns two `Block` objects, both with `kind=BlockKind.PARAGRAPH`. The first is not promoted to `HEADING` merely because it is short.

Known failure modes:

- Unknown legacy encodings may decode with replacement characters.
- Visual headings, page numbers, and verse cannot be recovered reliably from plain text alone.
- A renamed binary source without distinctive magic bytes may be rejected as `UNSUPPORTED_FORMAT` or `MALFORMED_DOCUMENT`.

### `MarkdownParser`

| Field | Value |
|---|---|
| Library | Python 3.12+ standard library; no external Markdown dependency is specified for v1 |
| `source_format` | `SourceFormat.MARKDOWN` |
| `ParserCapabilities` | `preserves_headings=True`, `preserves_page_numbers=False`, `is_lossy=True`, `is_async=False`, `requires_network=False`, `emits_confidence=False`, `emits_bboxes=False` |

`MarkdownParser` parses Markdown for structure only. ATX headings (`# Heading`) and setext headings become `HEADING` blocks, blockquotes become `QUOTE`, and list items become `LIST_ITEM`. Other prose blocks become `PARAGRAPH`.

Inline formatting is stripped before block text reaches the diff engine. A diff of prose should not report asterisks, underscores, or link delimiters as textual variants unless those characters are literally part of the text. This is slightly surprising but intentional: `*dark*` and `dark` compare as the same word by default because the scholar is comparing witness text, not Markdown markup.

Worked example:

```markdown
# Chapter 1

> Call me Ishmael.

- Some years ago
```

returns a `HEADING` block with `text="Chapter 1"`, a `QUOTE` block with `text="Call me Ishmael."`, and a `LIST_ITEM` block with `text="Some years ago"`.

Warnings can be emitted for unsupported embedded HTML, malformed list nesting, or links/images whose target text is discarded. Known failure modes are mostly structural: complex tables and inline HTML are not part of the v1 prose model and may flatten to `PARAGRAPH` with a warning.

### `DocxParser`

| Field | Value |
|---|---|
| Library | `python-docx` 1.2.0 |
| `source_format` | `SourceFormat.DOCX` |
| `ParserCapabilities` | `preserves_headings=True`, `preserves_page_numbers=False`, `is_lossy=True`, `is_async=False`, `requires_network=False`, `emits_confidence=False`, `emits_bboxes=False` |

`DocxParser` reads the main document body through `python-docx` 1.2.0. It maps `paragraph.style.name` to `BlockKind`:

| `paragraph.style.name` | `BlockKind` |
|---|---|
| `Heading 1` through `Heading 9` | `HEADING` |
| `Quote`, `Intense Quote` | `QUOTE` |
| Any style beginning with `List ` | `LIST_ITEM` |
| Anything else | `PARAGRAPH` |

The parser preserves headings, so `preserves_headings=True`. `Block.style` stores the original style name when available, while `Block.text` stores the normalized paragraph text. The document title comes from the optional upload title when provided; otherwise the parser may use package metadata or the filename. It must not invent a title from the first paragraph if that would remove the paragraph from the body.

Footnotes, endnotes, comments, and tracked changes are not in the main document body and are out of scope for v1. If detected, the parser emits an `IngestionWarning` stating that non-main-body material was not included in `blocks`.

Known failure modes:

- Corrupt ZIP containers or missing WordprocessingML parts return `MALFORMED_DOCUMENT`.
- Text in headers, footers, text boxes, comments, footnotes, and endnotes is not diffed in v1.
- Tracked changes may expose only the resolved main-body text available through `python-docx`.

### `PdfPlumberParser`

| Field | Value |
|---|---|
| Library | `pdfplumber` 0.11.x |
| `source_format` | `SourceFormat.PDF` |
| `ParserCapabilities` | `preserves_headings=False`, `preserves_page_numbers=True`, `is_lossy=True`, `is_async=False`, `requires_network=False`, `emits_confidence=False`, `emits_bboxes=False` |

`PdfPlumberParser` is the default PDF parser. It uses `pdfplumber` page character data (`page.chars`) for positional reconstruction; `extract_text(layout=True)` may be used as a diagnostic or fallback string, but block boundaries and reading order must be grounded in page geometry rather than raw content-stream order. PDF extraction is always lossy: the parser reconstructs prose from drawing instructions, not from a semantic document model.

Block reconstruction uses vertical gap analysis. Characters are grouped into lines by page and baseline proximity; adjacent lines join a candidate block when their vertical gap, left edge, and font-size band are consistent. Larger vertical gaps, indentation changes, and heading-like spacing start a new block. `Block.page` is populated from the source page. Heading preservation is not promised because PDF typography varies too much to make `HEADING` assignment reliable in v1.

Running heads, folio numbers, and footers become `ARTIFACT` blocks. The repeated-position heuristic records short text spans that recur on several pages at nearly the same vertical band and horizontal alignment. A recurring top-band string such as a chapter title, or a recurring bottom-band digit near the outer margin, is classified as `BlockKind.ARTIFACT` and excluded from the diff by default. See [Edge cases](./12-edge-cases.md) for the full treatment of PDF noise, hyphens, and layout artifacts.

Warnings can be emitted for low text density, uncertain reading order, repeated artifacts, dehyphenation decisions, or pages skipped because they contain no extractable text. Known failure modes include multi-column prose, marginalia, unusual writing directions, damaged fonts, and scanned PDFs.

### `PyPdfParser`

| Field | Value |
|---|---|
| Library | `pypdf` 6.14.2 |
| `source_format` | `SourceFormat.PDF` |
| `ParserCapabilities` | `preserves_headings=False`, `preserves_page_numbers=True`, `is_lossy=True`, `is_async=False`, `requires_network=False`, `emits_confidence=False`, `emits_bboxes=False` |

`PyPdfParser` is the fast path and fallback PDF parser. It uses `pypdf` 6.14.2 text extraction when the caller explicitly forces it, when deployment configuration disables `PdfPlumberParser`, or when a fast coarse extraction is preferable to positional reconstruction. It still sets `is_lossy=True` because PDF text order and layout semantics are reconstructed.

Blocks are derived from extracted page text by page-local paragraph breaks and whitespace normalization. Page numbers are preserved in `Block.page`, but character-level bounding boxes are not emitted. `PyPdfParser` should be expected to produce lower-fidelity block boundaries than `PdfPlumberParser`.

Known failure modes:

- Reading order may be wrong for multi-column or heavily positioned text.
- Running heads and folio numbers are harder to distinguish without character positions.
- Scanned PDFs still require OCR and must not produce silent empty documents.

## Detecting scanned PDFs

A PDF with pages but effectively no extractable text is almost certainly a scan. Both PDF parsers must sample up to five pages: the first page, the last page, and evenly spaced interior pages when present. After extraction and whitespace normalization, ingestion computes non-whitespace characters per sampled page. If the median sampled page has fewer than 20 non-whitespace characters and the PDF has at least one page, ingestion returns an RFC 9457 problem with `code="OCR_REQUIRED"`.

This is an honest v1 failure, not an empty `Document`. Returning an empty document would tell the diff engine that the witness contains no text, which is false. `OCR_REQUIRED` is the hand-off point to the OCR seam.

## The OCR extension seam

OCR is not implemented in v1, but the contracts are already shaped so that OCR does not alter downstream code.

```python
class AsyncDocumentParser(BaseDocumentParser):
    async def parse_async(self, source: DocumentSource) -> Document:
        """Parse the source witness asynchronously and return the same Document model.

        Async parsers must set ParserCapabilities.is_async=True. Callers must await this
        method rather than calling parse().
        """
        ...

    def parse(self, source):
        """Reject sync parsing for async-only parsers.

        The sync bridge raises SyncParseUnsupported so that API or job orchestration can
        await parse_async before persisting the same Document model.
        """
        raise SyncParseUnsupported(...)


class AsyncOCRParser(AsyncDocumentParser):
    """Future OCR parser seam; not implemented in v1."""

    ...
```

The important point is that the return type is still `Document`. Nothing in diffing, formatting, storage, or the frontend needs a separate OCR payload:

| Existing contract member | OCR use |
|---|---|
| `Block.confidence: float | None` | Per-block OCR confidence when available. |
| `Block.bbox: BoundingBox | None` | Page coordinates for mapping text back to the scanned image. |
| `DocumentMetadata.ocr_confidence` | Aggregate OCR confidence for the witness. |
| `ParserCapabilities.is_async` | Selects `parse_async` in API or job orchestration. |
| `ParserCapabilities.requires_network` | Allows a deployment to refuse cloud OCR in air-gapped environments. |
| `ParserCapabilities.emits_confidence` | Advertises confidence-bearing output. |
| `ParserCapabilities.emits_bboxes` | Advertises bounding-box-bearing output. |
| `SourceFormat.OCR` | Marks the source as OCR-derived while preserving the canonical `Document` model. |

The sync/async bridge is explicit. If code calls `parse()` on an async parser, `SyncParseUnsupported` is raised. The API or job orchestration must await `parse_async` before persisting the resulting `Document`; once that `Document` exists, the existing comparison path is unchanged. `ComparisonAccepted` remains the comparison endpoint's long-running response, not an ingestion payload. OCR may require an upload job contract in a later API revision, but it does not require any change to diffing or formatting.

A cloud OCR parser would set `requires_network=True`. A deployment configured for air-gapped research can then refuse that parser before any external request is attempted. A local OCR parser can set `requires_network=False`.

Illustrative sketch, not shipped in v1:

```python
class TesseractOCRParser(AsyncOCRParser):
    name = "tesseract-ocr"
    version = "<parser-version>"
    supported_extensions = frozenset({".pdf"})
    supported_media_types = frozenset({"application/pdf"})

    @classmethod
    def capabilities(cls) -> ParserCapabilities:
        return ParserCapabilities(
            preserves_headings=False,
            preserves_page_numbers=True,
            is_lossy=True,
            is_async=True,
            requires_network=False,
            emits_confidence=True,
            emits_bboxes=True,
        )

    async def parse_async(self, source: DocumentSource) -> Document:
        # OCR pages, group recognized lines into Block objects, and return Document.
        ...
```

The sketch does not introduce a new downstream type. It returns `Document` with `source_format=SourceFormat.OCR`, `Block.confidence`, optional `Block.bbox`, and `DocumentMetadata.ocr_confidence`.

## Adding a new parser

Contributors adding a parser must:

1. Implement `BaseDocumentParser` or `AsyncDocumentParser` in `backend/app/services/ingestion/`.
2. Use exact contract names: `ParserCapabilities`, `SourceProbe`, `DocumentSource`, `Document`, `Block`, `BlockKind`, `DocumentMetadata`, `IngestionWarning`, and `SourceFormat`.
3. Declare `name`, `version`, `supported_extensions`, and `supported_media_types`.
4. Implement cheap, side-effect-free `can_parse(probe)`.
5. Return canonical `Document` objects only; do not leak library-specific structures downstream.
6. Fill `char_start` and `char_end` offsets into reconstructed full text.
7. Emit `IngestionWarning` entries for recoverable data loss or extraction uncertainty.
8. Add the parser to the explicit `ParserRegistry` registration list in priority order.
9. Document capability values and known failure modes.
10. Add golden-corpus tests as described in [Testing strategy](./13-testing-strategy.md).
