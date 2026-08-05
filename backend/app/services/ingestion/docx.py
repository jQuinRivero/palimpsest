"""DOCX parser."""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from docx import Document as WordDocument
from docx.opc.exceptions import PackageNotFoundError

from app.models.document import BlockKind, Document, IngestionWarning, SourceFormat
from app.models.identifiers import new_document_id
from app.services.ingestion.base import (
    BaseDocumentParser,
    DocumentSource,
    ParserCapabilities,
    SourceProbe,
    SourceTooLargeError,
)
from app.services.ingestion.normalize import NormalizationBlock, normalize

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_ZIP_MAGIC = b"PK\x03\x04"
_WORD_DOCUMENT_PART = "word/document.xml"
_TRACKED_CHANGE_MARKERS = (b"<w:ins", b"<w:del")
_TEXT_BOX_MARKERS = (b"<w:txbxContent", b"<v:textbox", b"wps:txbx")
_DEFAULT_PARAGRAPH_STYLES = {"", "Normal", "Body Text"}


class DocxParser(BaseDocumentParser):
    """Parser for WordprocessingML DOCX witnesses."""

    name = "docx"
    version = "1"
    supported_extensions = frozenset({".docx"})
    supported_media_types = frozenset({_DOCX_MEDIA_TYPE})
    source_format = SourceFormat.DOCX

    @classmethod
    def capabilities(cls) -> ParserCapabilities:
        """Return static DOCX parser capabilities."""
        return ParserCapabilities(
            preserves_headings=True,
            preserves_page_numbers=False,
            is_lossy=True,
            is_async=False,
            requires_network=False,
            emits_confidence=False,
            emits_bboxes=False,
        )

    @classmethod
    def can_parse(cls, probe: SourceProbe) -> bool:
        """Return whether the probe is a genuine WordprocessingML package.

        A DOCX and an XLSX share the ZIP signature, so the deciding evidence is
        whether the archive contains ``word/document.xml``.

        When the probe holds the whole file that evidence is conclusive both
        ways, and a spreadsheet renamed to ``.docx`` is correctly refused.
        When the probe is only a prefix of a larger file the entry may simply
        lie beyond it, so fall back to the declared extension or media type and
        let ``parse`` make the authoritative check — it raises for a ZIP that
        turns out not to be a Word package, which the API maps to
        ``MALFORMED_DOCUMENT``.
        """
        declared = (
            probe.normalized_media_type in cls.supported_media_types
            or probe.extension in cls.supported_extensions
        )

        if probe.magic_bytes.startswith(_ZIP_MAGIC):
            if _has_word_document_part(probe.magic_bytes):
                return True
            # A complete archive that lacks the part is definitively not a DOCX.
            complete = len(probe.magic_bytes) >= probe.size_bytes
            return False if complete else declared

        if probe.magic_bytes:
            # Present but not a ZIP: this cannot be a DOCX whatever it claims.
            return False

        return declared

    def parse(self, source: DocumentSource) -> Document:
        """Read the main DOCX body and return a normalized document."""
        data = source.read_bytes()
        if not _has_word_document_part(data):
            raise ValueError("DOCX package is missing word/document.xml")

        # Before anything decompresses. Both the part read below and
        # python-docx's own unzipping are unbounded on their own, so the only
        # safe place for this is ahead of both of them.
        _assert_within_expansion_budget(data, source.max_decompressed_bytes)

        warnings = _detect_out_of_scope_content(data)
        try:
            package = WordDocument(BytesIO(data))
        except (BadZipFile, PackageNotFoundError) as exc:
            raise ValueError("DOCX package could not be opened") from exc

        blocks: list[NormalizationBlock] = []
        uncertain_styles: set[str] = set()
        for paragraph in package.paragraphs:
            text = paragraph.text
            if not text.strip():
                continue
            style = paragraph.style
            style_name = str(getattr(style, "name", "") or "")
            style_id = str(getattr(style, "style_id", "") or "")
            kind = _classify_style(style_name, style_id)
            if kind is BlockKind.PARAGRAPH and _style_mapping_is_uncertain(style_name, style_id):
                uncertain_styles.add(style_name or style_id)
            blocks.append(NormalizationBlock(text=text, kind=kind, style=style_name or None))

        warnings.extend(_style_warnings(uncertain_styles))
        return normalize(
            blocks,
            document_id=new_document_id(),
            title=_title_from_filename(source.filename),
            source_format=SourceFormat.DOCX,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            witness="a",
        )


def _assert_within_expansion_budget(data: bytes, budget: int) -> None:
    """Refuse a package that expands past ``budget``.

    The check reads the central directory and sums the declared uncompressed
    sizes. Nothing is decompressed, so a legitimate manuscript pays nothing and
    a bomb is refused before it can allocate anything.

    Declared sizes are written by whoever built the archive, so the obvious
    worry is an archive that under-declares and then over-delivers. It cannot,
    against this reader: ``zipfile`` stops a member at its declared length and
    then fails the CRC. Verified directly — an archive holding 8 MiB while
    declaring 1 KiB yields *zero* bytes and raises ``BadZipFile: Bad CRC-32``.
    python-docx reads through the same library, so the same bound applies to
    it. A second, streaming counter was written first and then removed: it
    would have decompressed every legitimate upload in full to defend against
    something this library already refuses.

    An archive that over-declares is rejected here, which is the conservative
    direction and costs an honest file nothing.
    """
    with ZipFile(BytesIO(data)) as archive:
        declared = sum(entry.file_size for entry in archive.infolist())

    if declared > budget:
        raise SourceTooLargeError(
            f"This document expands to {declared:,} bytes, over the "
            f"{budget:,} byte limit for a single upload."
        )


def _has_word_document_part(data: bytes) -> bool:
    """Return whether bytes contain the main WordprocessingML body part."""
    try:
        with ZipFile(BytesIO(data)) as archive:
            return _WORD_DOCUMENT_PART in archive.namelist()
    except BadZipFile:
        return False


def _detect_out_of_scope_content(data: bytes) -> list[IngestionWarning]:
    """Inspect DOCX package parts that python-docx omits from body paragraphs."""
    warnings: list[IngestionWarning] = []
    with ZipFile(BytesIO(data)) as archive:
        names = set(archive.namelist())
        document_xml = archive.read(_WORD_DOCUMENT_PART)
        if any(marker in document_xml for marker in _TRACKED_CHANGE_MARKERS):
            warnings.append(
                IngestionWarning(
                    code="TRACKED_CHANGES_IGNORED",
                    message=(
                        "Tracked changes are present; DOCX v1 uses only the resolved "
                        "main document body exposed by python-docx."
                    ),
                    block_id=None,
                )
            )
        if _has_any_part(names, ("word/comments.xml",)):
            warnings.append(
                IngestionWarning(
                    code="COMMENTS_IGNORED",
                    message="DOCX comments are outside the v1 main-body parser and were ignored.",
                    block_id=None,
                )
            )
        if _has_any_part(names, ("word/footnotes.xml",)):
            warnings.append(
                IngestionWarning(
                    code="FOOTNOTES_IGNORED",
                    message="DOCX footnotes are outside the v1 main-body parser and were ignored.",
                    block_id=None,
                )
            )
        if _has_any_part(names, ("word/endnotes.xml",)):
            warnings.append(
                IngestionWarning(
                    code="ENDNOTES_IGNORED",
                    message="DOCX endnotes are outside the v1 main-body parser and were ignored.",
                    block_id=None,
                )
            )
        if any(marker in document_xml for marker in _TEXT_BOX_MARKERS):
            warnings.append(
                IngestionWarning(
                    code="TEXT_BOXES_IGNORED",
                    message="DOCX text boxes are outside the v1 main-body parser and were ignored.",
                    block_id=None,
                )
            )
    return warnings


def _has_any_part(names: set[str], parts: Iterable[str]) -> bool:
    """Return whether any part exists in a DOCX package."""
    return any(part in names for part in parts)


def _classify_style(style_name: str, style_id: str) -> BlockKind:
    """Map Word paragraph styles to canonical block kinds."""
    normalized_name = style_name.strip()
    normalized_id = style_id.strip()
    if _is_heading_style(normalized_name, normalized_id):
        return BlockKind.HEADING
    if normalized_name in {"Quote", "Intense Quote"} or normalized_id in {"Quote", "IntenseQuote"}:
        return BlockKind.QUOTE
    if normalized_name.startswith("List") or normalized_id.startswith("List"):
        return BlockKind.LIST_ITEM
    return BlockKind.PARAGRAPH


def _is_heading_style(style_name: str, style_id: str) -> bool:
    """Return whether a style names a built-in heading in any supported locale."""
    if re_match := _heading_level(style_name, "Heading "):
        return re_match
    if re_match := _heading_level(style_name, "Título "):
        return re_match
    return bool(_heading_level(style_id, "Heading"))


def _heading_level(value: str, prefix: str) -> bool:
    suffix = value.removeprefix(prefix)
    return suffix != value and suffix.isdecimal() and 1 <= int(suffix) <= 9


def _style_mapping_is_uncertain(style_name: str, style_id: str) -> bool:
    """Return whether a non-default style was preserved but not structurally mapped."""
    style_label = style_name or style_id
    if style_label in _DEFAULT_PARAGRAPH_STYLES:
        return False
    return bool(style_label)


def _style_warnings(styles: set[str]) -> list[IngestionWarning]:
    """Build deterministic style classification warnings."""
    return [
        IngestionWarning(
            code="STYLE_MAPPING_UNCERTAIN",
            message=(
                f'DOCX style "{style}" was preserved on the block but classified as '
                "PARAGRAPH because it is not a known v1 structural style."
            ),
            block_id=None,
        )
        for style in sorted(styles)
    ]


def _title_from_filename(filename: str | None) -> str:
    """Return a stable display title derived from upload metadata."""
    if not filename:
        return "Untitled"
    return Path(filename).name
