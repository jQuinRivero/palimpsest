"""The probe prefix must be large enough to identify container formats.

A DOCX and an XLSX share the ZIP magic number, so distinguishing them means
reading far enough into the archive to see its entry names. An earlier version
of the API passed only eight bytes, which made `DocxParser.can_parse` reject
every genuine DOCX and produced `UNSUPPORTED_FORMAT` on valid uploads.

These tests exercise the probe exactly as the API constructs it.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document as WordDocument

from app.api.v1.documents import _MAGIC_BYTES
from app.services.ingestion.base import SourceProbe
from app.services.ingestion.docx import DocxParser
from app.services.ingestion.plaintext import PlainTextParser


def build_docx(paragraphs: list[str]) -> bytes:
    document = WordDocument()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_xlsx_like_zip() -> bytes:
    """A ZIP that is not a Word package."""
    import zipfile

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
    return buffer.getvalue()


def probe_as_api_would(data: bytes, filename: str, media_type: str) -> SourceProbe:
    """Construct the probe exactly as `POST /api/v1/documents` does."""
    return SourceProbe(
        filename=filename,
        media_type=media_type,
        magic_bytes=data[:_MAGIC_BYTES],
        size_bytes=len(data),
    )


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class TestProbePrefix:
    def test_prefix_is_large_enough_to_see_archive_entries(self) -> None:
        assert _MAGIC_BYTES >= 4096, (
            "The probe prefix must reach past the first ZIP entry, or DOCX "
            "detection silently fails."
        )

    def test_real_docx_is_claimed(self) -> None:
        data = build_docx(["It was a long crossing.", "The waves were grey."])
        probe = probe_as_api_would(data, "witness.docx", DOCX_MEDIA_TYPE)
        assert DocxParser.can_parse(probe) is True

    def test_large_docx_is_still_claimed(self) -> None:
        """A DOCX whose word/document.xml sits beyond the prefix."""
        data = build_docx([f"Paragraph number {n} of the manuscript." for n in range(400)])
        probe = probe_as_api_would(data, "long.docx", DOCX_MEDIA_TYPE)
        assert len(data) > _MAGIC_BYTES
        assert DocxParser.can_parse(probe) is True

    def test_plain_text_is_not_claimed(self) -> None:
        data = b"It was the best of times.\n"
        probe = probe_as_api_would(data, "witness.txt", "text/plain")
        assert DocxParser.can_parse(probe) is False
        assert PlainTextParser.can_parse(probe) is True

    def test_non_word_zip_is_rejected_or_fails_honestly(self) -> None:
        """A spreadsheet renamed to .docx must not silently produce a document."""
        data = build_xlsx_like_zip()
        probe = probe_as_api_would(data, "sheet.docx", DOCX_MEDIA_TYPE)

        if DocxParser.can_parse(probe):
            # Claimed on the declared extension; parse must then reject it.
            from app.services.ingestion.base import DocumentSource

            source = DocumentSource(
                filename="sheet.docx",
                media_type=DOCX_MEDIA_TYPE,
                size_bytes=len(data),
                data=data,
            )
            with pytest.raises(ValueError):
                DocxParser().parse(source)

    def test_docx_round_trips_through_the_parser(self) -> None:
        data = build_docx(["It was a long crossing.", "The waves were grey."])
        from app.services.ingestion.base import DocumentSource

        source = DocumentSource(
            filename="witness.docx",
            media_type=DOCX_MEDIA_TYPE,
            size_bytes=len(data),
            data=data,
        )
        document = DocxParser().parse(source)

        assert len(document.blocks) == 2
        assert document.blocks[0].text == "It was a long crossing."
        assert document.metadata.word_count == 9
