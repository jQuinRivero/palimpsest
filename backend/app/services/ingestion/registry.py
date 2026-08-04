"""Explicit parser registry and source-format detection."""

from __future__ import annotations

from app.services.ingestion.base import BaseDocumentParser, SourceProbe
from app.services.ingestion.plaintext import PlainTextParser

_TEXT_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")


class UnsupportedFormatError(Exception):
    """Raised when no registered parser can handle a source probe."""


class ParserRegistry:
    """Priority-ordered registry of explicitly registered parsers."""

    def __init__(self, parsers: list[type[BaseDocumentParser]] | None = None) -> None:
        """Create a registry using explicit priority order.

        Registration is deliberately not import-time magic: predictable startup
        avoids hidden plugin scans and makes deployment capabilities auditable.
        """
        self._parsers: list[type[BaseDocumentParser]] = []
        for parser in parsers or [PlainTextParser]:
            self.register(parser)

    def register(self, parser: type[BaseDocumentParser]) -> None:
        """Register a parser class at the end of the priority list.

        Parser names must be unique so forced selection and capabilities output
        are deterministic.
        """
        if any(existing.name == parser.name for existing in self._parsers):
            raise ValueError(f"parser {parser.name!r} is already registered")
        self._parsers.append(parser)

    def resolve(
        self,
        probe: SourceProbe,
        *,
        forced_name: str | None = None,
    ) -> type[BaseDocumentParser]:
        """Return the highest-priority parser compatible with the probe.

        Detection uses declared media type, filename extension, and magic bytes.
        Extension alone is insufficient: researchers rename files while
        transcribing, and a ``.txt`` may be UTF-16 text or a renamed ``.docx``.
        """
        if forced_name is not None:
            return self._resolve_forced(probe, forced_name)

        magic_matches = [parser for parser in self._parsers if _matches_magic(parser, probe)]
        if magic_matches:
            return magic_matches[0]

        media_matches = [
            parser
            for parser in self._parsers
            if probe.normalized_media_type in parser.supported_media_types
            and parser.can_parse(probe)
        ]
        if media_matches:
            return media_matches[0]

        extension_matches = [
            parser
            for parser in self._parsers
            if probe.extension in parser.supported_extensions and parser.can_parse(probe)
        ]
        if extension_matches:
            return extension_matches[0]

        raise UnsupportedFormatError(
            "No registered parser matched declared media type, file extension, or magic bytes"
        )

    def all_parsers(self) -> list[type[BaseDocumentParser]]:
        """Return registered parsers in deterministic priority order."""
        return list(self._parsers)

    def _resolve_forced(
        self,
        probe: SourceProbe,
        forced_name: str,
    ) -> type[BaseDocumentParser]:
        """Resolve a named parser only when it can parse the probe."""
        for parser in self._parsers:
            if parser.name == forced_name:
                if parser.can_parse(probe):
                    return parser
                raise UnsupportedFormatError(
                    f"Parser {forced_name!r} cannot parse the supplied source"
                )
        raise UnsupportedFormatError(f"Parser {forced_name!r} is not registered")


def _matches_magic(parser: type[BaseDocumentParser], probe: SourceProbe) -> bool:
    """Return whether magic bytes alone select this parser."""
    if not probe.magic_bytes:
        return False

    magic_only = SourceProbe(
        filename=None,
        media_type=None,
        magic_bytes=probe.magic_bytes,
        size_bytes=probe.size_bytes,
    )
    if parser.can_parse(magic_only):
        return True

    # Text files commonly have no container signature; BOMs are still a strong
    # encoding-family signal and should outrank a misleading extension.
    return bool(
        probe.magic_bytes.startswith(_TEXT_BOMS)
        and ".txt" in parser.supported_extensions
        and parser.can_parse(probe)
    )


DEFAULT_REGISTRY = ParserRegistry()
