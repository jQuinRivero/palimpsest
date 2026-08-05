"""PDF ingestion.

Two parsers share this module's helpers:

* :class:`PdfPlumberParser` is the default. It uses ``pdfplumber``'s
  character-level positional data, which is what makes running-head detection
  and gap-based block reconstruction possible at all.
* :class:`PyPdfParser` is a lighter fallback for simple, well-formed,
  single-column documents.

``PyMuPDF`` is deliberately absent. It is the better extractor and it is
AGPL-3.0, which is disqualifying in an Apache-2.0 project — see ADR-0002.

See docs/02-ingestion-and-parsers.md and docs/12-edge-cases.md.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from itertools import pairwise
from typing import Any, ClassVar

from app.models.document import (
    BlockKind,
    Document,
    IngestionWarning,
    SourceFormat,
)
from app.models.identifiers import new_document_id
from app.services.ingestion.base import (
    BaseDocumentParser,
    DocumentSource,
    ParserCapabilities,
    SourceProbe,
    SourceTooLargeError,
)
from app.services.ingestion.normalize import NormalizationBlock, normalize

_PDF_MAGIC = b"%PDF-"

#: A scanned page yields essentially nothing — there is no text layer at all,
#: so extraction returns zero characters or a few stray marks. The threshold is
#: therefore deliberately low: a legitimately sparse page (a title page, a part
#: divider, a page holding one line of verse) must not be mistaken for a scan,
#: and the cost of a false positive is refusing a document the researcher can
#: plainly read.
MIN_CHARS_PER_PAGE = 8

#: Never sample the whole of a long document just to answer "is this a scan?".
SCAN_SAMPLE_PAGES = 8

#: Fraction of page height treated as the header and footer bands, where
#: running heads and folio numbers live.
MARGIN_BAND = 0.09

#: A line must repeat in the same band on at least this many pages before it is
#: called an artifact. Guards against a short document whose first paragraph
#: happens to resemble its second.
MIN_ARTIFACT_PAGES = 3

#: ...or this fraction of pages, whichever is smaller, for short documents.
ARTIFACT_PAGE_RATIO = 0.5

#: A vertical gap larger than this multiple of the line leading starts a new
#: block. Paragraph leading is meaningfully larger than line leading.
BLOCK_GAP_RATIO = 1.6

#: Characters that end a sentence. A line ending in one of these at the foot of
#: a page probably ended a paragraph too.
_TERMINAL_PUNCTUATION = (".", "!", "?", '"', "\u201d", "\u2019", "'")

WARNING_READING_ORDER = "READING_ORDER_UNCERTAIN"
WARNING_MULTI_COLUMN = "MULTI_COLUMN_SUSPECTED"


class ScannedDocumentError(Exception):
    """The PDF has pages but no extractable text layer.

    Mapped to ``OCR_REQUIRED`` by the API. Returning an empty document instead
    would be a silent lie about a file the researcher can plainly read.
    """


class MalformedPdfError(Exception):
    """The PDF could not be opened or contains no pages."""


def _assert_within_page_budget(page_count: int, budget: int) -> None:
    """Refuse a document that declares more pages than anyone will read.

    A PDF states its own page count, and a small file can state a very large
    one — page objects are cheap and shareable. Every page is then examined,
    so the work a request costs is set by the file rather than by its size.
    Checked before the first page is touched.
    """
    if page_count > budget:
        raise SourceTooLargeError(
            f"This document declares {page_count:,} pages, over the "
            f"{budget:,} page limit for a single upload."
        )


@dataclass(frozen=True, slots=True)
class _Line:
    """One extracted line with the geometry needed to classify it."""

    text: str
    page: int
    top: float
    page_height: float

    @property
    def band(self) -> str:
        """Which vertical band of the page the line sits in."""
        if self.page_height <= 0:
            return "body"
        ratio = self.top / self.page_height
        if ratio <= MARGIN_BAND:
            return "header"
        if ratio >= 1 - MARGIN_BAND:
            return "footer"
        return "body"


def _normalise_repeat_key(text: str) -> str:
    """Collapse a line to what stays constant across pages.

    A running head is identical page to page; a folio number is not, so digits
    are masked. ``"CHAPTER ONE   17"`` and ``"CHAPTER ONE   18"`` share a key.
    """
    return "".join("#" if ch.isdigit() else ch for ch in text).strip().casefold()


def _artifact_keys(lines: list[_Line], page_count: int) -> set[str]:
    """Keys of header/footer lines that repeat across enough pages.

    Running heads and folio numbers are extracted for transparency but excluded
    from the diff by default: they are a property of the printing, not of the
    text, and diffing them reports differences no author made.
    """
    if page_count < 2:
        return set()

    threshold = min(MIN_ARTIFACT_PAGES, max(2, int(page_count * ARTIFACT_PAGE_RATIO)))
    pages_by_key: dict[str, set[int]] = {}

    for line in lines:
        if line.band == "body" or not line.text.strip():
            continue
        pages_by_key.setdefault(_normalise_repeat_key(line.text), set()).add(line.page)

    return {key for key, pages in pages_by_key.items() if len(pages) >= threshold}


def _looks_multi_column(chars: list[dict[str, Any]], page_width: float) -> bool:
    """Whether a page's characters cluster into separated vertical columns.

    Detection only; the honest response is a warning, because guessing a
    reading order for interleaved columns produces confident nonsense.
    """
    if not chars or page_width <= 0:
        return False

    midpoint = page_width / 2
    left = sum(1 for c in chars if float(c.get("x0", 0)) < midpoint * 0.9)
    right = sum(1 for c in chars if float(c.get("x0", 0)) > midpoint * 1.1)
    straddling = sum(1 for c in chars if midpoint * 0.9 <= float(c.get("x0", 0)) <= midpoint * 1.1)

    if not left or not right:
        return False
    balance = min(left, right) / max(left, right)
    return balance > 0.5 and straddling < len(chars) * 0.02


def _line_leading(lines: list[_Line]) -> float:
    """Estimate the leading between consecutive lines of the same paragraph.

    The *most common* gap, not the median: in a document with many short
    paragraphs the median is dragged toward the paragraph gap, and every
    paragraph break then looks ordinary. Line leading is by far the most
    frequently repeated vertical step in set prose.
    """
    gaps: list[float] = []
    for previous, current in pairwise(lines):
        if current.page == previous.page:
            gap = current.top - previous.top
            if gap > 0:
                gaps.append(round(gap, 1))

    if not gaps:
        return 0.0

    counts = Counter(gaps)
    most_common, frequency = counts.most_common(1)[0]
    if frequency > 1:
        return float(most_common)

    # Every gap is distinct, so there is no repeated leading to detect.
    # The smallest gap is the best available proxy for a single line step.
    return float(min(gaps))


def _group_into_blocks(lines: list[_Line], artifacts: set[str]) -> list[NormalizationBlock]:
    """Turn positioned lines into block candidates using vertical gaps."""
    if not lines:
        return []

    leading = _line_leading(lines)

    blocks: list[NormalizationBlock] = []
    buffer: list[str] = []
    buffer_page: int | None = None

    def flush() -> None:
        nonlocal buffer, buffer_page
        if buffer:
            blocks.append(
                NormalizationBlock(
                    text="\n".join(buffer),
                    kind=BlockKind.PARAGRAPH,
                    page=buffer_page,
                )
            )
            buffer = []
            buffer_page = None

    previous_line: _Line | None = None
    for line in lines:
        if _normalise_repeat_key(line.text) in artifacts:
            flush()
            blocks.append(
                NormalizationBlock(
                    text=line.text,
                    kind=BlockKind.ARTIFACT,
                    page=line.page,
                )
            )
            previous_line = line
            continue

        if previous_line is not None:
            new_page = line.page != previous_line.page
            gap = line.top - previous_line.top
            paragraph_break = leading > 0 and gap > leading * BLOCK_GAP_RATIO and not new_page

            # A page break is not automatically a paragraph break — a sentence
            # routinely runs across one, and splitting there would report a
            # difference the author never made. But when the previous page
            # ended on completed punctuation, a paragraph almost certainly
            # ended with it.
            if new_page and previous_line.text.rstrip().endswith(_TERMINAL_PUNCTUATION):
                paragraph_break = True

            if paragraph_break:
                flush()

        if buffer_page is None:
            buffer_page = line.page
        buffer.append(line.text)
        previous_line = line

    flush()
    return blocks


def _assert_has_text(blocks: list[NormalizationBlock], page_count: int) -> None:
    sampled = min(page_count, SCAN_SAMPLE_PAGES)
    characters = sum(len(block.text) for block in blocks)
    if sampled and characters / sampled < MIN_CHARS_PER_PAGE:
        raise ScannedDocumentError(
            f"Extracted only {characters} characters across {page_count} page(s). "
            "The document appears to be scanned and requires OCR, which is not "
            "available in this version."
        )


def _title_from_filename(filename: str | None) -> str:
    if not filename:
        return "Untitled"
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return stem.rsplit(".", 1)[0] or "Untitled"


class PdfPlumberParser(BaseDocumentParser):
    """Default PDF parser, using character-level positional data."""

    name: ClassVar[str] = "pdfplumber"
    version: ClassVar[str] = "1"
    supported_extensions: ClassVar[frozenset[str]] = frozenset({".pdf"})
    supported_media_types: ClassVar[frozenset[str]] = frozenset({"application/pdf"})
    source_format: ClassVar[SourceFormat] = SourceFormat.PDF

    @classmethod
    def capabilities(cls) -> ParserCapabilities:
        return ParserCapabilities(
            preserves_headings=False,
            preserves_page_numbers=True,
            # Layout is discarded, running heads are reclassified, and line
            # breaks are reflowed. The researcher is told so in the UI.
            is_lossy=True,
            is_async=False,
            requires_network=False,
            emits_confidence=False,
            emits_bboxes=False,
        )

    @classmethod
    def can_parse(cls, probe: SourceProbe) -> bool:
        if probe.magic_bytes:
            return probe.magic_bytes.startswith(_PDF_MAGIC)
        return (
            probe.normalized_media_type in cls.supported_media_types
            or probe.extension in cls.supported_extensions
        )

    def parse(self, source: DocumentSource) -> Document:
        import pdfplumber

        data = source.read_bytes()
        warnings: list[IngestionWarning] = []
        lines: list[_Line] = []

        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                page_count = len(pdf.pages)
                if not page_count:
                    raise MalformedPdfError("PDF contains no pages")
                _assert_within_page_budget(page_count, source.max_pages)

                for page_number, page in enumerate(pdf.pages, start=1):
                    height = float(page.height or 0)
                    chars: list[dict[str, Any]] = list(page.chars or [])

                    if _looks_multi_column(chars, float(page.width or 0)):
                        warnings.append(
                            IngestionWarning(
                                code=WARNING_MULTI_COLUMN,
                                message=(
                                    f"Page {page_number} appears to have multiple "
                                    "columns; extracted reading order may be "
                                    "interleaved."
                                ),
                                block_id=None,
                            )
                        )

                    for line in self._lines_from_page(page, page_number, height):
                        lines.append(line)
        except (ScannedDocumentError, MalformedPdfError, SourceTooLargeError):
            raise
        except Exception as exc:
            raise MalformedPdfError(f"PDF could not be read: {exc}") from exc

        artifacts = _artifact_keys(lines, page_count)
        blocks = _group_into_blocks(lines, artifacts)
        _assert_has_text(blocks, page_count)

        return normalize(
            blocks,
            document_id=new_document_id(),
            title=_title_from_filename(source.filename),
            source_format=SourceFormat.PDF,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            # A PDF's line breaks belong to the typesetter, not the author.
            reflow_lines=True,
        )

    @staticmethod
    def _lines_from_page(page: Any, page_number: int, height: float) -> list[_Line]:
        extracted: list[_Line] = []
        try:
            text_lines = page.extract_text_lines()
        except Exception:
            text_lines = None

        if text_lines:
            for entry in text_lines:
                text = str(entry.get("text", "")).strip()
                if text:
                    extracted.append(
                        _Line(
                            text=text,
                            page=page_number,
                            top=float(entry.get("top", 0.0)),
                            page_height=height,
                        )
                    )
            return extracted

        # Fall back to plain extraction, distributing lines evenly so that
        # band classification still has something to work with.
        raw = page.extract_text() or ""
        rows = [row.strip() for row in raw.split("\n") if row.strip()]
        for position, row in enumerate(rows):
            top = height * (position + 0.5) / max(1, len(rows))
            extracted.append(_Line(text=row, page=page_number, top=top, page_height=height))
        return extracted


class PyPdfParser(BaseDocumentParser):
    """Lighter fallback for simple, well-formed, single-column PDFs.

    Faster and dependency-light, but it has no positional data, so it cannot
    detect running heads, reconstruct paragraphs from vertical gaps, or notice
    a multi-column layout. Prefer :class:`PdfPlumberParser` unless the document
    is known to be plain.
    """

    name: ClassVar[str] = "pypdf"
    version: ClassVar[str] = "1"
    supported_extensions: ClassVar[frozenset[str]] = frozenset({".pdf"})
    supported_media_types: ClassVar[frozenset[str]] = frozenset({"application/pdf"})
    source_format: ClassVar[SourceFormat] = SourceFormat.PDF

    @classmethod
    def capabilities(cls) -> ParserCapabilities:
        return ParserCapabilities(
            preserves_headings=False,
            preserves_page_numbers=True,
            is_lossy=True,
            is_async=False,
            requires_network=False,
            emits_confidence=False,
            emits_bboxes=False,
        )

    @classmethod
    def can_parse(cls, probe: SourceProbe) -> bool:
        if probe.magic_bytes:
            return probe.magic_bytes.startswith(_PDF_MAGIC)
        return (
            probe.normalized_media_type in cls.supported_media_types
            or probe.extension in cls.supported_extensions
        )

    def parse(self, source: DocumentSource) -> Document:
        from pypdf import PdfReader

        data = source.read_bytes()
        try:
            reader = PdfReader(BytesIO(data))
            page_count = len(reader.pages)
            if not page_count:
                raise MalformedPdfError("PDF contains no pages")
            _assert_within_page_budget(page_count, source.max_pages)
            pages = [
                (number, page.extract_text() or "")
                for number, page in enumerate(reader.pages, start=1)
            ]
        except (MalformedPdfError, SourceTooLargeError):
            raise
        except Exception as exc:
            raise MalformedPdfError(f"PDF could not be read: {exc}") from exc

        blocks: list[NormalizationBlock] = []
        for page_number, text in pages:
            for chunk in text.split("\n\n"):
                stripped = chunk.strip()
                if stripped:
                    blocks.append(
                        NormalizationBlock(
                            text=stripped,
                            kind=BlockKind.PARAGRAPH,
                            page=page_number,
                        )
                    )

        _assert_has_text(blocks, page_count)

        return normalize(
            blocks,
            document_id=new_document_id(),
            title=_title_from_filename(source.filename),
            source_format=SourceFormat.PDF,
            parser_name=self.name,
            parser_version=self.version,
            warnings=[],
            reflow_lines=True,
        )
