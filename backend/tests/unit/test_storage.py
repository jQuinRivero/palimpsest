from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from app.models import (
    Block,
    BlockKind,
    BlockMetrics,
    BlockStatus,
    ComparisonResult,
    DiffBlock,
    DiffMetrics,
    DiffOptions,
    Document,
    DocumentMetadata,
    DocumentSummary,
    IngestionWarning,
    SourceFormat,
    Token,
    TokenStatus,
    check_comparison,
)
from app.storage import (
    ComparisonExpired,
    ComparisonNotFound,
    DocumentNotFound,
    SessionStore,
    SqliteSessionStore,
    sweep_expired,
)
from app.storage.sweeper import run_periodic_sweeper


def _document(document_id: str, title: str, *, expires_in: timedelta | None = None) -> Document:
    del expires_in
    block = Block(
        id=f"{document_id}-b0",
        index=0,
        kind=BlockKind.PARAGRAPH,
        text=f"{title} text",
        char_start=0,
        char_end=len(f"{title} text"),
    )
    return Document(
        id=document_id,
        title=title,
        source_format=SourceFormat.TXT,
        blocks=[block],
        metadata=DocumentMetadata(
            word_count=2,
            block_count=1,
            char_count=len(block.text),
            detected_language="en",
            parser_name="unit-test",
            parser_version="1.0",
        ),
        warnings=[IngestionWarning(code="UNIT_TEST", message="fixture warning", block_id=block.id)],
    )


def _unchanged_block(index: int, word: str) -> DiffBlock:
    token = Token(text=f"{word} ", status=TokenStatus.UNCHANGED)
    return DiffBlock(
        id=f"diff-{index}",
        status=BlockStatus.UNCHANGED,
        kind=BlockKind.PARAGRAPH,
        a_index=index,
        b_index=index,
        a_block_id=f"a-b{index}",
        b_block_id=f"b-b{index}",
        tokens=[token],
        a_tokens=[token],
        b_tokens=[token],
        metrics=BlockMetrics(
            similarity=1.0,
            edit_count=0,
            insertions=0,
            deletions=0,
            churn=0.0,
        ),
        move_distance=None,
        group_id=None,
    )


def _comparison(
    comparison_id: str,
    a: Document,
    b: Document,
    *,
    expires_at: datetime,
    block_count: int = 3,
) -> ComparisonResult:
    blocks = [_unchanged_block(index, f"word{index}") for index in range(block_count)]
    result = ComparisonResult(
        comparison_id=comparison_id,
        created_at=datetime(2026, 8, 4, 12, tzinfo=UTC),
        expires_at=expires_at,
        a=DocumentSummary.from_document(a),
        b=DocumentSummary.from_document(b),
        blocks=blocks,
        metrics=DiffMetrics(
            similarity=1.0,
            edit_count=0,
            insertions=0,
            deletions=0,
            unchanged_tokens=block_count,
            churn=0.0,
            blocks_moved=0,
            blocks_split=0,
            blocks_merged=0,
            a_word_count=block_count,
            b_word_count=block_count,
        ),
        options=DiffOptions(),
        truncated=False,
        total_blocks=block_count,
    )
    assert not check_comparison(result)
    return result


@pytest.fixture
def store() -> SqliteSessionStore:
    session_store = SqliteSessionStore(":memory:")
    yield session_store
    session_store.close()


def _put_document(
    store: SqliteSessionStore, document: Document, *, expires_at: datetime | None = None
) -> None:
    store.put_document(
        document,
        size_bytes=123,
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
    )


def test_round_trips_document_and_comparison(store: SqliteSessionStore) -> None:
    a = _document("doc-a", "Manuscript A")
    b = _document("doc-b", "Manuscript B")
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    _put_document(store, a, expires_at=expires_at)
    _put_document(store, b, expires_at=expires_at)
    comparison = _comparison("cmp-1", a, b, expires_at=expires_at)

    assert store.get_document(a.id) == a
    assert store.put_comparison(comparison, status="COMPLETE", expires_at=expires_at) == comparison
    assert store.get_comparison(comparison.comparison_id) == comparison


def test_pending_and_failed_comparison_status_round_trips(store: SqliteSessionStore) -> None:
    a = _document("doc-a", "Manuscript A")
    b = _document("doc-b", "Manuscript B")
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=1)
    _put_document(store, a, expires_at=expires_at)
    _put_document(store, b, expires_at=expires_at)

    pending = store.put_pending_comparison(
        comparison_id="cmp-pending",
        a=a,
        b=b,
        options=DiffOptions(),
        created_at=now,
        expires_at=expires_at,
    )
    record = store.get_comparison_record(pending.comparison_id)
    assert record.status == "PENDING"
    assert record.comparison.comparison_id == pending.comparison_id

    store.mark_comparison_failed(pending.comparison_id, "worker blew up")
    failed = store.get_comparison_record(pending.comparison_id)
    assert failed.status == "FAILED"
    assert failed.failure_detail == "worker blew up"


def test_expired_unswept_comparison_raises_expired(store: SqliteSessionStore) -> None:
    a = _document("doc-a", "Manuscript A")
    b = _document("doc-b", "Manuscript B")
    _put_document(store, a)
    _put_document(store, b)
    comparison = _comparison(
        "cmp-expired", a, b, expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )
    store.put_comparison(comparison, status="COMPLETE", expires_at=comparison.expires_at)

    with pytest.raises(ComparisonExpired):
        store.get_comparison(comparison.comparison_id)


def test_sweeper_deletes_expired_rows_and_leaves_live_rows(store: SqliteSessionStore) -> None:
    now = datetime.now(UTC)
    expired = _document("expired-doc", "Expired")
    live = _document("live-doc", "Live")
    other_live = _document("other-live-doc", "Other Live")
    _put_document(store, expired, expires_at=now - timedelta(seconds=1))
    _put_document(store, live, expires_at=now + timedelta(hours=1))
    _put_document(store, other_live, expires_at=now + timedelta(hours=1))
    live_comparison = _comparison("live-cmp", live, other_live, expires_at=now + timedelta(hours=1))
    store.put_comparison(live_comparison, status="COMPLETE", expires_at=live_comparison.expires_at)

    assert sweep_expired(store, now) == 1

    with pytest.raises(DocumentNotFound):
        store.get_document(expired.id)
    assert store.get_document(live.id) == live
    assert store.get_comparison(live_comparison.comparison_id) == live_comparison


def test_periodic_sweeper_deletes_expired_rows(store: SqliteSessionStore) -> None:
    now = datetime.now(UTC)
    expired = _document("expired-doc", "Expired")
    _put_document(store, expired, expires_at=now - timedelta(seconds=1))
    calls = 0

    async def sleep(_: float) -> object:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise asyncio.CancelledError
        return None

    async def run() -> None:
        with pytest.raises(asyncio.CancelledError):
            await run_periodic_sweeper(store, interval_seconds=0, sleep=sleep)

    asyncio.run(run())

    with pytest.raises(DocumentNotFound):
        store.get_document(expired.id)


def test_periodic_sweeper_survives_one_failed_pass() -> None:
    class FlakyStore:
        def __init__(self) -> None:
            self.calls = 0

        def sweep_expired(self, now: datetime) -> int:
            del now
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient")
            return 0

    store = FlakyStore()
    sleeps = 0

    async def sleep(_: float) -> object:
        nonlocal sleeps
        sleeps += 1
        if sleeps > 2:
            raise asyncio.CancelledError
        return None

    async def run() -> None:
        with pytest.raises(asyncio.CancelledError):
            await run_periodic_sweeper(
                cast(SessionStore, store),
                interval_seconds=0,
                sleep=sleep,
            )

    asyncio.run(run())

    assert store.calls == 2


def test_get_comparison_blocks_paging_and_limit_clamping(store: SqliteSessionStore) -> None:
    a = _document("doc-a", "Manuscript A")
    b = _document("doc-b", "Manuscript B")
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    _put_document(store, a, expires_at=expires_at)
    _put_document(store, b, expires_at=expires_at)
    comparison = _comparison("cmp-paged", a, b, expires_at=expires_at, block_count=4)
    store.put_comparison(comparison, status="COMPLETE", expires_at=expires_at)

    page = store.get_comparison_blocks(comparison.comparison_id, offset=1, limit=2)
    assert page.offset == 1
    assert page.limit == 2
    assert page.total_blocks == 4
    assert page.blocks == comparison.blocks[1:3]

    assert store.get_comparison_blocks(comparison.comparison_id, offset=10, limit=2).blocks == []
    clamped = store.get_comparison_blocks(comparison.comparison_id, offset=0, limit=999)
    assert clamped.limit == 500
    assert clamped.blocks == comparison.blocks
    defaulted = store.get_comparison_blocks(comparison.comparison_id, offset=-1, limit=0)
    assert defaulted.offset == 0
    assert defaulted.limit == 200


def test_unknown_ids_raise_not_found(store: SqliteSessionStore) -> None:
    with pytest.raises(DocumentNotFound):
        store.get_document("missing-doc")
    with pytest.raises(ComparisonNotFound):
        store.get_comparison("missing-cmp")
    with pytest.raises(ComparisonNotFound):
        store.get_comparison_blocks("missing-cmp", offset=0, limit=10)


def test_expired_source_document_expires_comparison_then_cascades_on_sweep(
    store: SqliteSessionStore,
) -> None:
    now = datetime.now(UTC)
    a = _document("doc-a", "Manuscript A")
    b = _document("doc-b", "Manuscript B")
    _put_document(store, a, expires_at=now - timedelta(seconds=1))
    _put_document(store, b, expires_at=now + timedelta(hours=1))
    comparison = _comparison("cmp-source-expired", a, b, expires_at=now + timedelta(hours=1))
    store.put_comparison(comparison, status="COMPLETE", expires_at=comparison.expires_at)

    with pytest.raises(ComparisonExpired):
        store.get_comparison(comparison.comparison_id)

    assert sweep_expired(store, now) == 1
    with pytest.raises(ComparisonNotFound):
        store.get_comparison(comparison.comparison_id)


def test_pragmas_are_applied(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.sqlite3"
    store = SqliteSessionStore(db_path)

    with store._connection() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode == "wal"
    assert synchronous == 1
    assert foreign_keys == 1
    assert busy_timeout == 5000

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
