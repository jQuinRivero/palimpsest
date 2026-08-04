"""Parser contracts for ingestion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, ClassVar

from app.models.document import Document, SourceFormat


@dataclass(frozen=True, slots=True)
class ParserCapabilities:
    """Static facts advertised by a parser implementation."""

    preserves_headings: bool
    preserves_page_numbers: bool
    is_lossy: bool
    is_async: bool
    requires_network: bool
    emits_confidence: bool
    emits_bboxes: bool


@dataclass(frozen=True, slots=True)
class SourceProbe:
    """Cheap source metadata used for parser selection."""

    filename: str | None
    media_type: str | None
    magic_bytes: bytes
    size_bytes: int

    @property
    def extension(self) -> str:
        """Return the lower-case filename extension, or an empty string.

        Implementations must treat this as one weak signal, not as proof of
        format, because researchers often rename exported witnesses.
        """
        if not self.filename:
            return ""
        return Path(self.filename).suffix.casefold()

    @property
    def normalized_media_type(self) -> str:
        """Return a lower-case media type without parameters."""
        if not self.media_type:
            return ""
        return self.media_type.split(";", maxsplit=1)[0].strip().casefold()


@dataclass(frozen=True, slots=True)
class DocumentSource:
    """Bytes plus upload metadata passed to a selected parser."""

    filename: str | None
    media_type: str | None
    size_bytes: int
    data: bytes | None = None
    stream: BinaryIO | None = None

    def read_bytes(self) -> bytes:
        """Return the source bytes without changing parser semantics.

        Callers must provide exactly one of ``data`` or ``stream``. Stream
        implementations are expected to be positioned at the beginning of the
        uploaded witness before parsing starts.
        """
        if (self.data is None) == (self.stream is None):
            raise ValueError("DocumentSource requires exactly one of data or stream")
        if self.data is not None:
            return self.data
        if self.stream is None:
            raise ValueError("DocumentSource stream is missing")
        return self.stream.read()


class SyncParseUnsupported(Exception):
    """Raised when sync code attempts to call an async-only parser."""


class BaseDocumentParser(ABC):
    """Base contract for parsers that turn one uploaded witness into a Document."""

    name: ClassVar[str]
    version: ClassVar[str]
    supported_extensions: ClassVar[frozenset[str]]
    supported_media_types: ClassVar[frozenset[str]]
    #: The format this parser produces. Reported by /api/v1/capabilities so the
    #: client can describe what it accepts without parsing anything.
    source_format: ClassVar[SourceFormat]

    @classmethod
    @abstractmethod
    def capabilities(cls) -> ParserCapabilities:
        """Return the static capabilities of this parser.

        Implementations must return the same value for a parser class for the
        life of the process. The registry and API layer use this to select the
        sync or async execution path and to tell researchers what fidelity to
        expect from the parser.
        """

    @classmethod
    @abstractmethod
    def can_parse(cls, probe: SourceProbe) -> bool:
        """Return whether this parser can parse the probed source.

        Implementations must decide from ``SourceProbe`` only. They must not
        consume a ``DocumentSource`` stream, perform network I/O, or parse the
        full document here. A true result means ``parse`` or ``parse_async`` is
        expected to return a canonical ``Document`` or raise a clear ingestion
        error for malformed input.
        """

    @abstractmethod
    def parse(self, source: DocumentSource) -> Document:
        """Parse the source witness and return a canonical Document.

        Implementations must invoke shared normalization or produce equivalent
        invariants: stable block ids, assigned ``BlockKind`` values, half-open
        offsets into ``Document.full_text()``, accurate metadata, and explicit
        ``IngestionWarning`` entries for recoverable uncertainty.
        """


class AsyncDocumentParser(BaseDocumentParser):
    """Base class for parsers that cannot be called synchronously."""

    @abstractmethod
    async def parse_async(self, source: DocumentSource) -> Document:
        """Parse the source witness asynchronously and return a Document.

        Implementations must set ``ParserCapabilities.is_async=True`` and must
        return the same canonical model as sync parsers. Callers must await this
        method rather than calling ``parse``.
        """

    def parse(self, source: DocumentSource) -> Document:
        """Reject synchronous parsing for async-only parsers.

        The API or job orchestration layer must call ``parse_async`` before
        persisting the resulting ``Document``.
        """
        raise SyncParseUnsupported(f"{self.name} must be parsed asynchronously")
