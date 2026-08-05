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


#: Ceiling on what one source may become once decompressed, used when a caller
#: supplies no budget of its own.
#:
#: Deliberately a real number rather than "unlimited". The upload cap bounds
#: *compressed* bytes, and a ZIP can expand by three orders of magnitude, so a
#: parser reached through some path that forgot to set a budget must still be
#: bounded. Sized well above any manuscript this tool will collate — the token
#: ceiling puts that at a few megabytes of text, tens of megabytes as
#: WordprocessingML — and far below anything that threatens the process.
DEFAULT_MAX_DECOMPRESSED_BYTES = 128 * 1024 * 1024

#: Ceiling on pages in one source, used when a caller supplies no limit.
#:
#: A PDF's page count is read from its own structure and can be large for a
#: small file, and every page is then examined. A 100k-word manuscript runs to
#: a few hundred pages, so this leaves an order of magnitude of headroom while
#: refusing a document nobody intends to read.
DEFAULT_MAX_PAGES = 5_000


class SourceTooLargeError(Exception):
    """A witness costs more to read than the caller is willing to spend.

    Distinct from a malformed source: the file is perfectly well formed and is
    simply too expensive — an archive that expands enormously, or a document
    declaring more pages than anyone will read. That is a different answer to
    give the researcher, and a different one to give a monitoring system.
    """


@dataclass(frozen=True, slots=True)
class DocumentSource:
    """Bytes plus upload metadata passed to a selected parser."""

    filename: str | None
    media_type: str | None
    size_bytes: int
    data: bytes | None = None
    stream: BinaryIO | None = None
    #: What this source is allowed to become once decompressed. Carried with
    #: the source rather than read from configuration, because ingestion does
    #: not know about configuration — the API layer supplies it.
    max_decompressed_bytes: int = DEFAULT_MAX_DECOMPRESSED_BYTES
    #: How many pages this source may declare before it is refused unread.
    max_pages: int = DEFAULT_MAX_PAGES

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
