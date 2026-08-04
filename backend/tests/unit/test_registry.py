from __future__ import annotations

from typing import ClassVar

import pytest

from app.models.document import Document
from app.services.ingestion.base import (
    BaseDocumentParser,
    DocumentSource,
    ParserCapabilities,
    SourceProbe,
)
from app.services.ingestion.plaintext import PlainTextParser
from app.services.ingestion.registry import ParserRegistry, UnsupportedFormatError


class _StubParser(BaseDocumentParser):
    name: ClassVar[str] = "stub"
    version: ClassVar[str] = "1"
    supported_extensions: ClassVar[frozenset[str]] = frozenset()
    supported_media_types: ClassVar[frozenset[str]] = frozenset()
    magic: ClassVar[bytes] = b""

    @classmethod
    def capabilities(cls) -> ParserCapabilities:
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
        return (
            bool(cls.magic and probe.magic_bytes.startswith(cls.magic))
            or probe.normalized_media_type in cls.supported_media_types
            or probe.extension in cls.supported_extensions
        )

    def parse(self, source: DocumentSource) -> Document:
        raise NotImplementedError


class MagicParser(_StubParser):
    name: ClassVar[str] = "magic"
    magic: ClassVar[bytes] = b"MAGIC"


class MediaParser(_StubParser):
    name: ClassVar[str] = "media"
    supported_media_types: ClassVar[frozenset[str]] = frozenset({"application/x-test"})


class ExtensionParser(_StubParser):
    name: ClassVar[str] = "extension"
    supported_extensions: ClassVar[frozenset[str]] = frozenset({".test"})


def test_resolves_by_magic_bytes() -> None:
    registry = ParserRegistry([MagicParser])

    parser = registry.resolve(
        SourceProbe(filename=None, media_type=None, magic_bytes=b"MAGIC-data", size_bytes=10)
    )

    assert parser is MagicParser


def test_resolves_by_declared_media_type() -> None:
    registry = ParserRegistry([MediaParser])

    parser = registry.resolve(
        SourceProbe(
            filename=None,
            media_type="application/x-test; charset=utf-8",
            magic_bytes=b"",
            size_bytes=0,
        )
    )

    assert parser is MediaParser


def test_resolves_by_extension() -> None:
    registry = ParserRegistry([ExtensionParser])

    parser = registry.resolve(
        SourceProbe(filename="witness.test", media_type=None, magic_bytes=b"", size_bytes=0)
    )

    assert parser is ExtensionParser


def test_magic_precedes_media_and_extension() -> None:
    registry = ParserRegistry([ExtensionParser, MediaParser, MagicParser])

    parser = registry.resolve(
        SourceProbe(
            filename="witness.test",
            media_type="application/x-test",
            magic_bytes=b"MAGIC-data",
            size_bytes=10,
        )
    )

    assert parser is MagicParser


def test_priority_breaks_ties_within_same_signal() -> None:
    class FirstExtension(ExtensionParser):
        name: ClassVar[str] = "first-extension"

    class SecondExtension(ExtensionParser):
        name: ClassVar[str] = "second-extension"

    registry = ParserRegistry([FirstExtension, SecondExtension])

    parser = registry.resolve(
        SourceProbe(filename="witness.test", media_type=None, magic_bytes=b"", size_bytes=0)
    )

    assert parser is FirstExtension


def test_no_match_raises_clear_error() -> None:
    registry = ParserRegistry([PlainTextParser])

    with pytest.raises(UnsupportedFormatError, match="No registered parser matched"):
        registry.resolve(
            SourceProbe(
                filename="witness.bin",
                media_type="application/octet-stream",
                magic_bytes=b"\x00\x01",
                size_bytes=2,
            )
        )
