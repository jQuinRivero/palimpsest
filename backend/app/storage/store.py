"""Storage protocol for expiring document and comparison sessions.

The protocol is intentional rather than decorative: SQLite under WAL permits
many concurrent readers but still serializes writes through one writer. A
horizontally scaled deployment must therefore swap the implementation instead
of treating one SQLite file as a shared write backend. Structural typing keeps
that seam explicit without coupling callers to the v1 SQLite store.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.models import BlockPage, ComparisonResult, Document, DocumentSummary


class DocumentNotFound(Exception):
    """A document id is unknown or its cache entry has expired."""


class ComparisonNotFound(Exception):
    """A comparison id is unknown."""


class ComparisonExpired(Exception):
    """A comparison or one of its source documents has expired."""


class SessionStore(Protocol):
    def put_document(
        self, document: Document, *, size_bytes: int, expires_at: datetime
    ) -> DocumentSummary:
        """Persist one parsed witness until ``expires_at``."""

    def get_document(self, document_id: str) -> Document:
        """Return a live document, or raise ``DocumentNotFound``."""

    def delete_document(self, document_id: str) -> None:
        """Delete a document and any comparisons that reference it."""

    def put_comparison(
        self, comparison: ComparisonResult, *, status: str, expires_at: datetime
    ) -> ComparisonResult:
        """Persist one comparison result until ``expires_at``."""

    def get_comparison(self, comparison_id: str) -> ComparisonResult:
        """Return a live comparison, or raise a storage exception."""

    def get_comparison_blocks(self, comparison_id: str, offset: int, limit: int) -> BlockPage:
        """Return a window of live comparison blocks."""

    def delete_comparison(self, comparison_id: str) -> None:
        """Delete a comparison if it exists."""

    def sweep_expired(self, now: datetime) -> int:
        """Delete expired rows and return the number of directly deleted rows."""
