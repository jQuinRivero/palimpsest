"""Storage protocol for expiring document and comparison sessions.

The protocol is intentional rather than decorative: SQLite under WAL permits
many concurrent readers but still serializes writes through one writer. A
horizontally scaled deployment must therefore swap the implementation instead
of treating one SQLite file as a shared write backend. Structural typing keeps
that seam explicit without coupling callers to the v1 SQLite store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.models import BlockPage, ComparisonResult, Document, DocumentSummary
from app.models.diff import DiffOptions


class DocumentNotFound(Exception):
    """A document id is unknown or its cache entry has expired."""


class ComparisonNotFound(Exception):
    """A comparison id is unknown."""


class ComparisonExpired(Exception):
    """A comparison or one of its source documents has expired."""


class ComparisonFailed(Exception):
    """A background comparison reached a terminal failure state."""


@dataclass(frozen=True)
class ComparisonRecord:
    """Stored comparison plus its job status."""

    comparison: ComparisonResult
    status: str
    failure_detail: str | None = None


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

    def put_pending_comparison(
        self,
        *,
        comparison_id: str,
        a: Document,
        b: Document,
        options: DiffOptions,
        created_at: datetime,
        expires_at: datetime,
    ) -> ComparisonResult:
        """Persist a comparison shell before background computation."""

    def mark_comparison_failed(self, comparison_id: str, detail: str) -> None:
        """Mark a pending comparison as failed."""

    def get_comparison(self, comparison_id: str) -> ComparisonResult:
        """Return a live comparison, or raise a storage exception."""

    def get_comparison_record(self, comparison_id: str) -> ComparisonRecord:
        """Return a live comparison row with its job status."""

    def get_comparison_blocks(self, comparison_id: str, offset: int, limit: int) -> BlockPage:
        """Return a window of live comparison blocks."""

    def delete_comparison(self, comparison_id: str) -> None:
        """Delete a comparison if it exists."""

    def sweep_expired(self, now: datetime) -> int:
        """Delete expired rows and return the number of directly deleted rows."""
