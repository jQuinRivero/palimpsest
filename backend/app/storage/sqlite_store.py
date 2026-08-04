"""SQLite implementation of the session cache."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast
from uuid import uuid4

from app.models import (
    BlockPage,
    ComparisonResult,
    DiffBlock,
    DiffMetrics,
    DiffOptions,
    Document,
    DocumentMetadata,
    DocumentSummary,
    IngestionWarning,
)
from app.storage.store import ComparisonExpired, ComparisonNotFound, DocumentNotFound

SCHEMA_VERSION: Final = 1
DEFAULT_BLOCK_LIMIT: Final = 200
MAX_BLOCK_LIMIT: Final = 500


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


def _text(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _expired(expires_at: str, now: datetime) -> bool:
    return _parse(expires_at) <= now


class SqliteSessionStore:
    """SessionStore backed by one SQLite database file."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._uri = False
        self._keeper: sqlite3.Connection | None = None
        if self._path == ":memory:":
            self._path = f"file:palimpsest-session-store-{uuid4().hex}?mode=memory&cache=shared"
            self._uri = True
            self._keeper = self._connect()
        self._bootstrap()

    def close(self) -> None:
        if self._keeper is not None:
            self._keeper.close()
            self._keeper = None

    def put_document(
        self, document: Document, *, size_bytes: int, expires_at: datetime
    ) -> DocumentSummary:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (
                  id, title, source_format, blocks_json, metadata_json, warnings_json,
                  created_at, expires_at, size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.id,
                    document.title,
                    document.source_format.value,
                    json.dumps([block.model_dump(mode="json") for block in document.blocks]),
                    document.metadata.model_dump_json(),
                    json.dumps([warning.model_dump(mode="json") for warning in document.warnings]),
                    _text(_now()),
                    _text(expires_at),
                    size_bytes,
                ),
            )
        return DocumentSummary.from_document(document)

    def get_document(self, document_id: str) -> Document:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, title, source_format, blocks_json, metadata_json, warnings_json,
                       expires_at
                FROM documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None or _expired(str(row["expires_at"]), _now()):
            raise DocumentNotFound(document_id)
        return Document.model_validate(
            {
                "id": row["id"],
                "title": row["title"],
                "source_format": row["source_format"],
                "blocks": json.loads(str(row["blocks_json"])),
                "metadata": DocumentMetadata.model_validate_json(str(row["metadata_json"])),
                "warnings": [
                    IngestionWarning.model_validate(item)
                    for item in json.loads(str(row["warnings_json"]))
                ],
            }
        )

    def delete_document(self, document_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def put_comparison(
        self, comparison: ComparisonResult, *, status: str, expires_at: datetime
    ) -> ComparisonResult:
        stored = comparison.model_copy(update={"expires_at": _utc(expires_at)})
        with self._connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO comparisons (
                      id, a_document_id, b_document_id, options_json, metrics_json,
                      blocks_json, created_at, expires_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored.comparison_id,
                        stored.a.id,
                        stored.b.id,
                        stored.options.model_dump_json(),
                        stored.metrics.model_dump_json(),
                        json.dumps([block.model_dump(mode="json") for block in stored.blocks]),
                        _text(stored.created_at),
                        _text(stored.expires_at),
                        status,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DocumentNotFound("comparison source document is missing") from exc
        return stored

    def get_comparison(self, comparison_id: str) -> ComparisonResult:
        row = self._comparison_row(comparison_id)
        return self._comparison_from_row(row)

    def get_comparison_blocks(self, comparison_id: str, offset: int, limit: int) -> BlockPage:
        row = self._comparison_row(comparison_id)
        blocks_payload = json.loads(str(row["blocks_json"]))
        total_blocks = len(blocks_payload)
        safe_offset = max(offset, 0)
        safe_limit = DEFAULT_BLOCK_LIMIT if limit <= 0 else min(MAX_BLOCK_LIMIT, limit)
        page = blocks_payload[safe_offset : safe_offset + safe_limit]
        return BlockPage(
            blocks=[DiffBlock.model_validate(block) for block in page],
            offset=safe_offset,
            limit=safe_limit,
            total_blocks=total_blocks,
        )

    def delete_comparison(self, comparison_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM comparisons WHERE id = ?", (comparison_id,))

    def sweep_expired(self, now: datetime) -> int:
        deadline = _text(now)
        with self._connection() as conn:
            comparison_cursor = conn.execute(
                "DELETE FROM comparisons WHERE expires_at <= ?",
                (deadline,),
            )
            document_cursor = conn.execute(
                "DELETE FROM documents WHERE expires_at <= ?",
                (deadline,),
            )
            conn.execute("PRAGMA optimize")
        return max(comparison_cursor.rowcount, 0) + max(document_cursor.rowcount, 0)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, uri=self._uri)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _bootstrap(self) -> None:
        with self._connection() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'schema_migrations'
                """
            ).fetchone()
            if exists is None:
                schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
                conn.executescript(schema)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _text(_now())),
                )

    def _comparison_row(self, comparison_id: str) -> sqlite3.Row:
        with self._connection() as conn:
            row = cast(
                sqlite3.Row | None,
                conn.execute(
                    """
                SELECT c.id, c.a_document_id, c.b_document_id, c.options_json, c.metrics_json,
                       c.blocks_json, c.created_at, c.expires_at, c.status,
                       a.id AS a_id, a.title AS a_title, a.source_format AS a_source_format,
                       a.metadata_json AS a_metadata_json, a.warnings_json AS a_warnings_json,
                       a.expires_at AS a_expires_at,
                       b.id AS b_id, b.title AS b_title, b.source_format AS b_source_format,
                       b.metadata_json AS b_metadata_json, b.warnings_json AS b_warnings_json,
                       b.expires_at AS b_expires_at
                FROM comparisons c
                LEFT JOIN documents a ON a.id = c.a_document_id
                LEFT JOIN documents b ON b.id = c.b_document_id
                WHERE c.id = ?
                """,
                    (comparison_id,),
                ).fetchone(),
            )
        if row is None:
            raise ComparisonNotFound(comparison_id)

        now = _now()
        if _expired(str(row["expires_at"]), now):
            raise ComparisonExpired(comparison_id)
        if row["a_id"] is None or row["b_id"] is None:
            raise ComparisonExpired(comparison_id)
        if _expired(str(row["a_expires_at"]), now) or _expired(str(row["b_expires_at"]), now):
            raise ComparisonExpired(comparison_id)
        return row

    def _comparison_from_row(self, row: sqlite3.Row) -> ComparisonResult:
        blocks_payload = json.loads(str(row["blocks_json"]))
        return ComparisonResult(
            comparison_id=str(row["id"]),
            created_at=_parse(str(row["created_at"])),
            expires_at=_parse(str(row["expires_at"])),
            a=self._summary_from_row(row, "a"),
            b=self._summary_from_row(row, "b"),
            blocks=[DiffBlock.model_validate(block) for block in blocks_payload],
            metrics=DiffMetrics.model_validate_json(str(row["metrics_json"])),
            options=DiffOptions.model_validate_json(str(row["options_json"])),
            truncated=False,
            total_blocks=len(blocks_payload),
        )

    def _summary_from_row(self, row: sqlite3.Row, prefix: str) -> DocumentSummary:
        return DocumentSummary(
            id=str(row[f"{prefix}_id"]),
            title=str(row[f"{prefix}_title"]),
            source_format=str(row[f"{prefix}_source_format"]),
            metadata=DocumentMetadata.model_validate_json(str(row[f"{prefix}_metadata_json"])),
            warnings=[
                IngestionWarning.model_validate(item)
                for item in json.loads(str(row[f"{prefix}_warnings_json"]))
            ],
        )
