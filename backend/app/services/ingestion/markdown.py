"""Markdown parser."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.document import BlockKind, Document, IngestionWarning, SourceFormat
from app.models.identifiers import new_document_id
from app.services.ingestion.base import (
    BaseDocumentParser,
    DocumentSource,
    ParserCapabilities,
    SourceProbe,
)
from app.services.ingestion.normalize import NormalizationBlock, normalize

_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"
_BINARY_CONTAINER_MAGICS = (b"%PDF-", b"PK\x03\x04")
_ATX_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
_SETEXT_HEADING = re.compile(r"^[ \t]*(=+|-+)[ \t]*$")
_BLOCKQUOTE = re.compile(r"^[ \t]*>[ \t]?(.*)$")
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|[0-9]+[.)])[ \t]+(.+)$")
_FENCE = re.compile(r"^[ \t]*(```+|~~~+)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_CODE = re.compile(r"`([^`]+)`")
_STRONG = re.compile(r"(\*\*|__)(.+?)\1")
_EMPHASIS = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)|(?<!_)_([^_\n]+)_(?!_)")


class MarkdownParser(BaseDocumentParser):
    """Parser for Markdown witnesses."""

    name = "markdown"
    version = "1"
    supported_extensions = frozenset({".md", ".markdown"})
    supported_media_types = frozenset({"text/markdown", "text/x-markdown"})
    source_format = SourceFormat.MARKDOWN

    @classmethod
    def capabilities(cls) -> ParserCapabilities:
        """Return static Markdown parser capabilities."""
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
        """Return whether the probe is compatible with Markdown parsing."""
        if probe.magic_bytes.startswith(_BINARY_CONTAINER_MAGICS):
            return False
        if probe.magic_bytes.startswith((_UTF8_BOM, _UTF16_LE_BOM, _UTF16_BE_BOM)):
            return probe.extension in cls.supported_extensions
        return (
            probe.normalized_media_type in cls.supported_media_types
            or probe.extension in cls.supported_extensions
        )

    def parse(self, source: DocumentSource) -> Document:
        """Decode Markdown bytes and return a normalized document."""
        data = source.read_bytes()
        text, warnings = _decode_text(data)
        blocks, inline_was_stripped = _parse_blocks(text)
        if inline_was_stripped:
            warnings.append(
                IngestionWarning(
                    code="MARKDOWN_INLINE_STRIPPED",
                    message=(
                        "Markdown inline formatting was stripped so prose diffs compare "
                        "visible text rather than markup delimiters."
                    ),
                    block_id=None,
                )
            )
        return normalize(
            blocks,
            document_id=new_document_id(),
            title=_title_from_filename(source.filename),
            source_format=SourceFormat.MARKDOWN,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            witness="a",
        )


def _decode_text(data: bytes) -> tuple[str, list[IngestionWarning]]:
    """Decode Markdown bytes according to the text parser policy."""
    if data.startswith(_UTF8_BOM):
        return data.decode("utf-8-sig"), []
    if data.startswith((_UTF16_LE_BOM, _UTF16_BE_BOM)):
        return data.decode("utf-16"), []
    try:
        return data.decode("utf-8"), []
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), [
            IngestionWarning(
                code="MARKDOWN_DECODING_REPLACEMENT",
                message=(
                    "Markdown was not valid UTF-8 and had no BOM; invalid byte "
                    "sequences were decoded with replacement characters."
                ),
                block_id=None,
            )
        ]


def _parse_blocks(text: str) -> tuple[list[NormalizationBlock], bool]:
    """Parse Markdown block structure without using an external dependency."""
    blocks: list[NormalizationBlock] = []
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_fence = False
    inline_was_stripped = False
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0

    def flush_paragraph() -> None:
        nonlocal inline_was_stripped
        if not paragraph_lines:
            return
        stripped_text, stripped = _strip_inline_formatting(" ".join(paragraph_lines))
        inline_was_stripped = inline_was_stripped or stripped
        blocks.append(NormalizationBlock(text=stripped_text, kind=BlockKind.PARAGRAPH))
        paragraph_lines.clear()

    def flush_code() -> None:
        if code_lines:
            blocks.append(NormalizationBlock(text="\n".join(code_lines), kind=BlockKind.ARTIFACT))
        code_lines.clear()

    while index < len(lines):
        line = lines[index]
        if _FENCE.match(line):
            if in_fence:
                flush_code()
                in_fence = False
            else:
                flush_paragraph()
                in_fence = True
            index += 1
            continue

        if in_fence:
            code_lines.append(line)
            index += 1
            continue

        if not line.strip():
            flush_paragraph()
            index += 1
            continue

        heading = _ATX_HEADING.match(line)
        if heading:
            flush_paragraph()
            heading_text, stripped = _strip_inline_formatting(heading.group(2).strip())
            inline_was_stripped = inline_was_stripped or stripped
            blocks.append(NormalizationBlock(text=heading_text, kind=BlockKind.HEADING))
            index += 1
            continue

        if index + 1 < len(lines) and _SETEXT_HEADING.match(lines[index + 1]) and line.strip():
            flush_paragraph()
            heading_text, stripped = _strip_inline_formatting(line.strip())
            inline_was_stripped = inline_was_stripped or stripped
            blocks.append(NormalizationBlock(text=heading_text, kind=BlockKind.HEADING))
            index += 2
            continue

        quote = _BLOCKQUOTE.match(line)
        if quote:
            flush_paragraph()
            quote_text, stripped = _strip_inline_formatting(quote.group(1).strip())
            inline_was_stripped = inline_was_stripped or stripped
            blocks.append(NormalizationBlock(text=quote_text, kind=BlockKind.QUOTE))
            index += 1
            continue

        list_item = _LIST_ITEM.match(line)
        if list_item:
            flush_paragraph()
            item_text, stripped = _strip_inline_formatting(list_item.group(1).strip())
            inline_was_stripped = inline_was_stripped or stripped
            blocks.append(NormalizationBlock(text=item_text, kind=BlockKind.LIST_ITEM))
            index += 1
            continue

        paragraph_lines.append(line.strip())
        index += 1

    if in_fence:
        flush_code()
    flush_paragraph()
    return blocks, inline_was_stripped


def _strip_inline_formatting(text: str) -> tuple[str, bool]:
    """Strip Markdown inline delimiters while preserving visible label text."""
    original = text
    # Markdown markup is source formatting, not witness prose; stripping it
    # prevents asterisks, backticks, and link delimiters from polluting diffs.
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _CODE.sub(r"\1", text)
    text = _STRONG.sub(r"\2", text)
    text = _EMPHASIS.sub(lambda match: match.group(1) or match.group(2) or "", text)
    return text, text != original


def _title_from_filename(filename: str | None) -> str:
    """Return a stable display title derived from upload metadata."""
    if not filename:
        return "Untitled"
    return Path(filename).name
