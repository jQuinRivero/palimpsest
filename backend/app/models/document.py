"""Canonical document model.

Produced by ingestion, consumed by the diff engine. Every parser returns this
shape regardless of source format, which is the invariant that lets a future
OCR parser be added without touching anything downstream.

See docs/05-data-schema.md — that document is normative for these definitions.
"""

from __future__ import annotations

# StrEnum requires Python 3.11+. If the interpreter pin in pyproject.toml is
# ever lowered, every enum here must become `class X(str, Enum)`.
from enum import StrEnum

from pydantic import BaseModel, Field


class BlockKind(StrEnum):
    """What a block is, structurally."""

    PARAGRAPH = "PARAGRAPH"
    HEADING = "HEADING"
    VERSE_LINE = "VERSE_LINE"
    QUOTE = "QUOTE"
    LIST_ITEM = "LIST_ITEM"
    #: Running head, folio number, footer. Extracted for transparency but
    #: excluded from the diff by default.
    ARTIFACT = "ARTIFACT"


class SourceFormat(StrEnum):
    """The format a witness arrived in.

    ``OCR`` is reachable by no parser in v1. It exists now so that activating
    the OCR pipeline is not a schema change.
    """

    TXT = "TXT"
    MARKDOWN = "MARKDOWN"
    DOCX = "DOCX"
    PDF = "PDF"
    OCR = "OCR"


class BoundingBox(BaseModel):
    """Position of a block on a source page. Reserved for OCR."""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float


class Block(BaseModel):
    """The atomic unit of alignment: a paragraph, heading, or verse line."""

    id: str
    #: 0-based ordinal. This is the number shown in the change gutter — a block
    #: index, never a rendered visual line number, because prose reflows.
    index: int
    kind: BlockKind
    #: Normalized text. See docs/03-normalization.md.
    text: str
    #: Source style name such as "Heading 1". Diagnostic only; never drives the diff.
    style: str | None = None
    #: 1-based page number, PDF only.
    page: int | None = None
    #: Half-open offsets into the document's reconstructed full text.
    char_start: int
    char_end: int
    #: True when this block opens a stanza. Set during verse segmentation,
    #: which is the only point at which the blank line between stanzas still
    #: exists; false for prose, which does not begin stanzas. See ADR-0007.
    starts_stanza: bool = False
    #: Reserved for OCR; null for every v1 parser.
    confidence: float | None = None
    bbox: BoundingBox | None = None


class IngestionWarning(BaseModel):
    """Something the parser had to guess at, surfaced rather than hidden."""

    code: str
    message: str
    block_id: str | None = None


class DocumentMetadata(BaseModel):
    word_count: int
    block_count: int
    char_count: int
    #: BCP 47 tag.
    detected_language: str | None = None
    parser_name: str
    parser_version: str
    #: Reserved for OCR.
    ocr_confidence: float | None = None


class Document(BaseModel):
    """One parsed witness."""

    id: str
    title: str
    source_format: SourceFormat
    blocks: list[Block]
    metadata: DocumentMetadata
    warnings: list[IngestionWarning] = Field(default_factory=list)

    def full_text(self) -> str:
        """Reconstruct the text that ``char_start``/``char_end`` index into."""
        return "\n\n".join(block.text for block in self.blocks)


class DocumentSummary(BaseModel):
    """A ``Document`` without its blocks.

    Embedded in ``ComparisonResult`` so the payload describes both witnesses
    without carrying two full copies of the source text alongside the diff.
    """

    id: str
    title: str
    source_format: SourceFormat
    metadata: DocumentMetadata
    warnings: list[IngestionWarning] = Field(default_factory=list)

    @classmethod
    def from_document(cls, document: Document) -> DocumentSummary:
        return cls(
            id=document.id,
            title=document.title,
            source_format=document.source_format,
            metadata=document.metadata,
            warnings=document.warnings,
        )
