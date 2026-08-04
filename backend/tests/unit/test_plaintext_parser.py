from __future__ import annotations

from app.models.document import BlockKind, Document
from app.services.ingestion.base import DocumentSource, SourceProbe
from app.services.ingestion.plaintext import PlainTextParser


def _parse(data: bytes, filename: str = "witness.txt") -> Document:
    return PlainTextParser().parse(
        DocumentSource(
            filename=filename,
            media_type="text/plain",
            size_bytes=len(data),
            data=data,
        )
    )


def test_utf8_bom_is_removed() -> None:
    document = _parse(b"\xef\xbb\xbfCafe")

    assert document.full_text() == "Cafe"
    assert not document.warnings


def test_utf16_boms_are_decoded() -> None:
    le_document = _parse(b"\xff\xfe" + "Café".encode("utf-16-le"), filename="le.txt")
    be_document = _parse(b"\xfe\xff" + "Café".encode("utf-16-be"), filename="be.txt")

    assert le_document.full_text() == "Café"
    assert be_document.full_text() == "Café"
    assert not le_document.warnings
    assert not be_document.warnings


def test_malformed_utf8_emits_warning_and_replacement() -> None:
    document = _parse(b"abc\xffdef")

    assert document.full_text() == "abc\ufffddef"
    assert [warning.code for warning in document.warnings] == ["TEXT_DECODING_REPLACEMENT"]


def test_empty_input_produces_empty_document() -> None:
    document = _parse(b"")

    assert document.blocks == []
    assert document.full_text() == ""
    assert document.metadata.word_count == 0
    assert document.metadata.block_count == 0
    assert document.metadata.char_count == 0


def test_blank_lines_segment_blocks() -> None:
    document = _parse(b"First block\n\nSecond  block\ttext")

    assert [block.text for block in document.blocks] == ["First block", "Second block text"]
    assert [block.char_start for block in document.blocks] == [0, len("First block\n\n")]
    assert [block.char_end for block in document.blocks] == [
        len("First block"),
        len("First block\n\nSecond block text"),
    ]
    assert document.full_text()[document.blocks[1].char_start : document.blocks[1].char_end] == (
        "Second block text"
    )


def test_capabilities_match_plaintext_heading_behavior() -> None:
    capabilities = PlainTextParser.capabilities()
    document = _parse(b"A Short Title\n\nThe body.")

    assert capabilities.preserves_headings is False
    assert [block.kind for block in document.blocks] == [BlockKind.PARAGRAPH, BlockKind.PARAGRAPH]


def test_plaintext_can_parse_declared_signals() -> None:
    assert PlainTextParser.can_parse(
        SourceProbe(filename="witness.txt", media_type=None, magic_bytes=b"", size_bytes=0)
    )
    assert PlainTextParser.can_parse(
        SourceProbe(filename=None, media_type="text/plain", magic_bytes=b"", size_bytes=0)
    )
    assert PlainTextParser.can_parse(
        SourceProbe(filename=None, media_type=None, magic_bytes=b"\xff\xfeA", size_bytes=3)
    )
