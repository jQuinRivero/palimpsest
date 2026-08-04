"""Ingestion services."""

from app.services.ingestion.base import (
    AsyncDocumentParser,
    BaseDocumentParser,
    DocumentSource,
    ParserCapabilities,
    SourceProbe,
    SyncParseUnsupported,
)
from app.services.ingestion.normalize import NormalizationBlock, normalize
from app.services.ingestion.plaintext import PlainTextParser
from app.services.ingestion.registry import DEFAULT_REGISTRY, ParserRegistry, UnsupportedFormatError

__all__ = [
    "DEFAULT_REGISTRY",
    "AsyncDocumentParser",
    "BaseDocumentParser",
    "DocumentSource",
    "NormalizationBlock",
    "ParserCapabilities",
    "ParserRegistry",
    "PlainTextParser",
    "SourceProbe",
    "SyncParseUnsupported",
    "UnsupportedFormatError",
    "normalize",
]
