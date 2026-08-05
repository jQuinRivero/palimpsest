"""Bounding what one upload can cost.

The upload cap counts compressed bytes. A ZIP expands by up to three orders of
magnitude, so without a second limit a 25 MiB `.docx` becomes tens of
gigabytes and takes the process with it. Measured before the guard existed: a
120 KiB archive expanded to 120 MiB, the parser returned normally, and peak
allocation was 262 MiB.

These tests are deliberately built around archives that are refused rather
than survived. A fixture that actually produced gigabytes would be worse than
the bug it tests.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.services.ingestion.base import (
    DEFAULT_MAX_DECOMPRESSED_BYTES,
    DEFAULT_MAX_PAGES,
    DocumentSource,
    SourceTooLargeError,
)
from app.services.ingestion.docx import DocxParser
from app.services.ingestion.pdf import PdfPlumberParser

WORD_PART = "word/document.xml"
CONTENT_TYPES = (
    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
    'package/2006/content-types"/>'
)


def archive(part_bytes: bytes, *, extra: dict[str, bytes] | None = None) -> bytes:
    """A ZIP shaped like a DOCX, with a main part of the given content."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr(WORD_PART, part_bytes)
        for name, blob in (extra or {}).items():
            zf.writestr(name, blob)
    return buffer.getvalue()


def source(data: bytes, *, budget: int = DEFAULT_MAX_DECOMPRESSED_BYTES) -> DocumentSource:
    return DocumentSource(
        filename="witness.docx",
        media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        size_bytes=len(data),
        data=data,
        max_decompressed_bytes=budget,
    )


class TestExpansionIsBounded:
    def test_a_high_ratio_archive_is_refused(self) -> None:
        # Eight mebibytes of one repeated byte compresses to a few kibibytes.
        bomb = archive(b"<" + b"A" * (8 * 1024 * 1024) + b">")

        assert len(bomb) < 64 * 1024, "fixture should be small; that is the point"

        with pytest.raises(SourceTooLargeError, match="expands to"):
            DocxParser().parse(source(bomb, budget=1024 * 1024))

    def test_the_refusal_names_both_numbers(self) -> None:
        """A researcher told only 'too large' cannot tell what to change."""
        bomb = archive(b"A" * (4 * 1024 * 1024))
        with zipfile.ZipFile(io.BytesIO(bomb)) as zf:
            declared = sum(entry.file_size for entry in zf.infolist())

        with pytest.raises(SourceTooLargeError) as raised:
            DocxParser().parse(source(bomb, budget=64 * 1024))

        message = str(raised.value)
        assert f"{declared:,}" in message
        assert "65,536" in message

    def test_many_small_members_are_summed(self) -> None:
        """The budget is for the package, not for its largest part."""
        extra = {f"word/media/image{i}.bin": b"B" * (256 * 1024) for i in range(8)}
        package = archive(b"<w:document/>", extra=extra)

        with pytest.raises(SourceTooLargeError):
            DocxParser().parse(source(package, budget=1024 * 1024))

    def test_a_legitimate_package_is_not_refused(self) -> None:
        """The expensive failure is refusing a real manuscript."""
        package = archive(b"<w:document/>", extra={"word/media/a.png": b"C" * (2 * 1024 * 1024)})

        # Parsing fails later for not being real WordprocessingML; what matters
        # is that it is not refused for size.
        with pytest.raises(Exception) as raised:
            DocxParser().parse(source(package, budget=DEFAULT_MAX_DECOMPRESSED_BYTES))

        assert not isinstance(raised.value, SourceTooLargeError)

    def test_the_default_budget_applies_when_none_is_given(self) -> None:
        """A caller that forgets must still be bounded, not unlimited."""
        assert DEFAULT_MAX_DECOMPRESSED_BYTES > 0

        plain = DocumentSource(
            filename="witness.docx",
            media_type=None,
            size_bytes=1,
            data=b"x",
        )
        assert plain.max_decompressed_bytes == DEFAULT_MAX_DECOMPRESSED_BYTES


class TestDeclaredSizesAreTrustworthyHere:
    """Why summing the central directory is enough.

    The guard trusts sizes written by whoever built the archive, which looks
    unsafe. It is safe against this reader, and this is the evidence: a member
    cannot deliver more than it declares, because ``zipfile`` stops at the
    declared length and then fails the CRC.

    If a future Python changes that, these fail and the guard needs the
    streaming counter that was written and then removed as unnecessary.
    """

    def lying(self, real: bytes, claimed: int) -> bytes:
        """An archive whose headers under-declare the size of its member."""
        data = bytearray(archive(real))
        claimed_bytes = claimed.to_bytes(4, "little")

        # Local file header: uncompressed size at +22 from the signature.
        local = data.find(b"PK\x03\x04", data.find(WORD_PART.encode()) - 64)
        data[local + 22 : local + 26] = claimed_bytes

        # Central directory: uncompressed size at +24 from the signature.
        central = data.rfind(b"PK\x01\x02")
        while central != -1:
            name_length = int.from_bytes(data[central + 28 : central + 30], "little")
            name = bytes(data[central + 46 : central + 46 + name_length])
            if name == WORD_PART.encode():
                data[central + 24 : central + 28] = claimed_bytes
                break
            central = data.rfind(b"PK\x01\x02", 0, central)

        return bytes(data)

    def test_a_member_cannot_deliver_more_than_it_declares(self) -> None:
        real = b"A" * (2 * 1024 * 1024)
        package = self.lying(real, claimed=1024)

        with zipfile.ZipFile(io.BytesIO(package)) as zf:
            info = zf.getinfo(WORD_PART)
            assert info.file_size == 1024, "fixture should under-declare"

            delivered = 0
            with (
                pytest.raises(zipfile.BadZipFile, match="CRC"),
                zf.open(info) as member,
            ):
                while chunk := member.read(64 * 1024):
                    delivered += len(chunk)

        assert delivered <= 1024, "reader must not exceed the declared length"


class TestPageCountIsBounded:
    """A PDF states its own page count and every page is then examined.

    Page objects are cheap and shareable, so a small file can ask for a great
    deal of work. The count is checked before the first page is touched.
    """

    def test_a_document_declaring_too_many_pages_is_refused(self) -> None:
        from tests.pdf_builder import build_pdf, prose_page

        pages = [prose_page(f"Page {i} of the witness.") for i in range(6)]
        data = build_pdf(pages)

        with pytest.raises(SourceTooLargeError, match="pages"):
            PdfPlumberParser().parse(
                DocumentSource(
                    filename="many.pdf",
                    media_type="application/pdf",
                    size_bytes=len(data),
                    data=data,
                    max_pages=3,
                )
            )

    def test_an_ordinary_document_is_not_refused(self) -> None:
        from tests.pdf_builder import build_pdf, prose_page

        data = build_pdf([prose_page("A single ordinary page of prose here.")])

        document = PdfPlumberParser().parse(
            DocumentSource(
                filename="one.pdf",
                media_type="application/pdf",
                size_bytes=len(data),
                data=data,
                max_pages=DEFAULT_MAX_PAGES,
            )
        )
        assert document.blocks

    def test_the_default_page_budget_applies_when_none_is_given(self) -> None:
        plain = DocumentSource(filename="x.pdf", media_type=None, size_bytes=1, data=b"x")
        assert plain.max_pages == DEFAULT_MAX_PAGES
