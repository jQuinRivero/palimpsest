from __future__ import annotations

from app.models.document import BlockKind, Document
from app.services.ingestion.base import DocumentSource, SourceProbe
from app.services.ingestion.markdown import MarkdownParser


def _parse(data: bytes, filename: str = "witness.md") -> Document:
    return MarkdownParser().parse(
        DocumentSource(
            filename=filename,
            media_type="text/markdown",
            size_bytes=len(data),
            data=data,
        )
    )


def test_markdown_can_parse_declared_signals() -> None:
    assert MarkdownParser.can_parse(
        SourceProbe(filename="witness.md", media_type=None, magic_bytes=b"", size_bytes=0)
    )
    assert MarkdownParser.can_parse(
        SourceProbe(filename="witness.markdown", media_type=None, magic_bytes=b"", size_bytes=0)
    )
    assert MarkdownParser.can_parse(
        SourceProbe(filename=None, media_type="text/markdown", magic_bytes=b"", size_bytes=0)
    )
    assert MarkdownParser.can_parse(
        SourceProbe(filename=None, media_type="text/x-markdown", magic_bytes=b"", size_bytes=0)
    )


def test_markdown_rejects_binary_containers() -> None:
    assert not MarkdownParser.can_parse(
        SourceProbe(
            filename="witness.md", media_type="text/markdown", magic_bytes=b"%PDF-", size_bytes=5
        )
    )
    assert not MarkdownParser.can_parse(
        SourceProbe(
            filename="witness.md",
            media_type="text/markdown",
            magic_bytes=b"PK\x03\x04",
            size_bytes=4,
        )
    )


def test_block_kind_assignment_for_markdown_syntax() -> None:
    document = _parse(
        b"# ATX heading\n\nSetext heading\n---\n\n> Quoted line\n\n- Bullet\n* Star\n+ Plus\n1. Ordered\n\nParagraph text\n\n```python\nprint('not prose')\n```"
    )

    assert [block.kind for block in document.blocks] == [
        BlockKind.HEADING,
        BlockKind.HEADING,
        BlockKind.QUOTE,
        BlockKind.LIST_ITEM,
        BlockKind.LIST_ITEM,
        BlockKind.LIST_ITEM,
        BlockKind.LIST_ITEM,
        BlockKind.PARAGRAPH,
        BlockKind.ARTIFACT,
    ]
    assert [block.text for block in document.blocks] == [
        "ATX heading",
        "Setext heading",
        "Quoted line",
        "Bullet",
        "Star",
        "Plus",
        "Ordered",
        "Paragraph text",
        "print('not prose')",
    ]


def test_inline_formatting_is_stripped_and_warned_once() -> None:
    document = _parse(b"**Bold** and *italic* plus `code` and [label](https://example.test).")

    assert document.full_text() == "Bold and italic plus code and label."
    assert [warning.code for warning in document.warnings] == ["MARKDOWN_INLINE_STRIPPED"]


def test_capabilities_match_markdown_heading_behavior() -> None:
    capabilities = MarkdownParser.capabilities()
    document = _parse(b"# Chapter 1\n\nBody")

    assert capabilities.preserves_headings is True
    assert [block.kind for block in document.blocks] == [
        BlockKind.HEADING,
        BlockKind.PARAGRAPH,
    ]


def test_empty_input_produces_empty_document() -> None:
    document = _parse(b"")

    assert document.blocks == []
    assert document.full_text() == ""
    assert document.metadata.word_count == 0
    assert document.metadata.block_count == 0
    assert document.metadata.char_count == 0


def test_malformed_utf8_emits_warning_and_replacement() -> None:
    document = _parse(b"abc\xffdef")

    assert document.full_text() == "abc\ufffddef"
    assert [warning.code for warning in document.warnings] == ["MARKDOWN_DECODING_REPLACEMENT"]
