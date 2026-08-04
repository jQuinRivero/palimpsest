"""Plain text parser."""

from __future__ import annotations

from pathlib import Path

from app.models.document import Document, IngestionWarning, SourceFormat
from app.models.identifiers import new_document_id
from app.services.ingestion.base import (
    BaseDocumentParser,
    DocumentSource,
    ParserCapabilities,
    SourceProbe,
)
from app.services.ingestion.normalize import normalize

_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"
_BINARY_CONTAINER_MAGICS = (b"%PDF-", b"PK\x03\x04")


class PlainTextParser(BaseDocumentParser):
    """Parser for ``text/plain`` witnesses."""

    name = "plaintext"
    version = "1"
    supported_extensions = frozenset({".txt"})
    supported_media_types = frozenset({"text/plain"})
    source_format = SourceFormat.TXT

    @classmethod
    def capabilities(cls) -> ParserCapabilities:
        """Return static plaintext parser capabilities.

        Plain text does not reliably preserve headings, page numbers,
        confidence, or bounding boxes; it decodes the complete text without
        lossy structural extraction.
        """
        return ParserCapabilities(
            preserves_headings=False,
            preserves_page_numbers=False,
            is_lossy=False,
            is_async=False,
            requires_network=False,
            emits_confidence=False,
            emits_bboxes=False,
        )

    @classmethod
    def can_parse(cls, probe: SourceProbe) -> bool:
        """Return whether the probe is compatible with plain text parsing.

        The decision is based only on cheap metadata. Container magics win over
        extension/media-type hints so a renamed binary document is not silently
        decoded as replacement-character text.
        """
        if probe.magic_bytes.startswith(_BINARY_CONTAINER_MAGICS):
            return False
        if probe.magic_bytes.startswith((_UTF8_BOM, _UTF16_LE_BOM, _UTF16_BE_BOM)):
            return True
        return (
            probe.normalized_media_type in cls.supported_media_types
            or probe.extension in cls.supported_extensions
        )

    def parse(self, source: DocumentSource) -> Document:
        """Decode the source bytes and return a normalized TXT document.

        Encoding resolution is BOM-first, then strict UTF-8, then UTF-8 with
        replacement plus an ``IngestionWarning`` so decoding uncertainty is
        never hidden from researchers.
        """
        data = source.read_bytes()
        text, warnings = _decode_text(data)
        return normalize(
            text,
            document_id=new_document_id(),
            title=_title_from_filename(source.filename),
            source_format=SourceFormat.TXT,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            witness="a",
        )


def _decode_text(data: bytes) -> tuple[str, list[IngestionWarning]]:
    """Decode bytes according to the deterministic plaintext policy."""
    if data.startswith(_UTF8_BOM):
        return data.decode("utf-8-sig"), []
    if data.startswith((_UTF16_LE_BOM, _UTF16_BE_BOM)):
        return data.decode("utf-16"), []
    try:
        return data.decode("utf-8"), []
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), [
            IngestionWarning(
                code="TEXT_DECODING_REPLACEMENT",
                message=(
                    "Plain text was not valid UTF-8 and had no BOM; invalid byte "
                    "sequences were decoded with replacement characters."
                ),
                block_id=None,
            )
        ]


def _title_from_filename(filename: str | None) -> str:
    """Return a stable display title derived from upload metadata."""
    if not filename:
        return "Untitled"
    return Path(filename).name
