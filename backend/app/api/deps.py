"""Shared API dependencies: the session store and the parser registry."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends

from app.config import Settings, get_settings
from app.services.ingestion.docx import DocxParser
from app.services.ingestion.markdown import MarkdownParser
from app.services.ingestion.pdf import PdfPlumberParser, PyPdfParser
from app.services.ingestion.plaintext import PlainTextParser
from app.services.ingestion.registry import ParserRegistry
from app.storage.sqlite_store import SqliteSessionStore


@lru_cache
def get_registry() -> ParserRegistry:
    """Parsers are registered explicitly rather than discovered at import time.

    Startup is then predictable and there is no hidden plugin scanning.

    Order is priority order. ``PdfPlumberParser`` precedes ``PyPdfParser``
    because both claim ``application/pdf`` and pdfplumber's positional analysis
    is what makes running-head detection and gap-based paragraph
    reconstruction possible; pypdf remains available by explicit selection as a
    faster, lower-fidelity path.

    Adding the future OCR parser is a one-line change here and nothing else in
    the application — the client builds its accept list from
    ``GET /api/v1/capabilities``.
    """
    return ParserRegistry(
        [
            PlainTextParser,
            MarkdownParser,
            DocxParser,
            PdfPlumberParser,
            PyPdfParser,
        ]
    )


@lru_cache
def _store_for(path: str) -> SqliteSessionStore:
    return SqliteSessionStore(path)


def get_store(settings: Settings = Depends(get_settings)) -> Iterator[SqliteSessionStore]:
    """Yield the session store.

    ``settings`` must be declared with ``Depends``; a plain default would make
    FastAPI treat ``Settings`` as a request body field and silently wrap every
    endpoint's body in an envelope.
    """
    yield _store_for(settings.database_path)
