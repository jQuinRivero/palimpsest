"""Comparison creation and retrieval."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.deps import get_store
from app.api.errors import ApiError
from app.config import Settings, get_settings
from app.models.api import (
    ComparisonAccepted,
    ComparisonStatus,
    CreateComparisonRequest,
    ErrorCode,
)
from app.models.diff import BlockPage, ComparisonResult
from app.models.identifiers import new_comparison_id
from app.services.diffing.engine import DiffBudgetExceeded
from app.services.formatting.payload import build_comparison
from app.services.formatting.tei import build_tei
from app.storage.sqlite_store import SqliteSessionStore
from app.storage.store import (
    ComparisonExpired,
    ComparisonNotFound,
    DocumentNotFound,
    SessionStore,
)
from app.storage.sweeper import sweep_expired

logger = logging.getLogger(__name__)


class _Bucket:
    def __init__(self, *, capacity: int, refill_per_second: float) -> None:
        self.capacity = float(capacity)
        self.refill_per_second = refill_per_second
        self.tokens = float(capacity)
        self.updated_at = time.monotonic()

    def take(self) -> float | None:
        now = time.monotonic()
        elapsed = now - self.updated_at
        self.updated_at = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return None
        if self.refill_per_second <= 0:
            return 60.0
        return (1.0 - self.tokens) / self.refill_per_second


_rate_lock = threading.Lock()
_buckets: dict[tuple[str, int, int], _Bucket] = {}


async def _run_configured_sweeper(settings: Settings) -> None:
    while True:
        await asyncio.sleep(settings.sweeper_interval_seconds)
        store = SqliteSessionStore(settings.database_path)
        try:
            await asyncio.to_thread(sweep_expired, store)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduled session cache sweep failed")
        finally:
            store.close()


@asynccontextmanager
async def _lifespan(app: object) -> AsyncIterator[None]:
    overrides = getattr(app, "dependency_overrides", {})
    settings_override = overrides.get(get_settings) if isinstance(overrides, dict) else None
    settings = settings_override() if callable(settings_override) else get_settings()
    task: asyncio.Task[None] | None = None
    if settings.sweeper_enabled:
        task = asyncio.create_task(_run_configured_sweeper(settings))
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


router = APIRouter(prefix="/comparisons", tags=["comparisons"], lifespan=_lifespan)


def _no_store(response: Response) -> None:
    """Uploaded manuscripts may be unpublished and are nobody else's to keep.

    Comparisons are unguessable but not secret, so they must never be indexed
    by a crawler or retained by an intermediary cache.
    """
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "private, no-store"


def _load(store: SessionStore, comparison_id: str) -> ComparisonResult:
    try:
        return store.get_comparison(comparison_id)
    except ComparisonExpired as exc:
        # 410 rather than 404: the resource existed and is knowably gone, so
        # the client should not retry.
        raise ApiError(
            ErrorCode.COMPARISON_EXPIRED,
            f"Comparison {comparison_id} has expired.",
        ) from exc
    except ComparisonNotFound as exc:
        raise ApiError(
            ErrorCode.COMPARISON_NOT_FOUND,
            f"No comparison with id {comparison_id}.",
        ) from exc


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.rate_limit_enabled:
        return

    capacity = max(settings.rate_limit_burst, 1)
    refill_per_second = max(settings.rate_limit_requests_per_minute, 0) / 60.0
    key = (_client_ip(request), capacity, settings.rate_limit_requests_per_minute)

    with _rate_lock:
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = _Bucket(capacity=capacity, refill_per_second=refill_per_second)
            _buckets[key] = bucket
        retry_after = bucket.take()

    if retry_after is not None:
        seconds = max(1, math.ceil(retry_after))
        raise ApiError(
            ErrorCode.RATE_LIMITED,
            "Too many requests; retry after the indicated delay.",
            headers={"Retry-After": str(seconds)},
        )


def _within_inline_budget(
    a_blocks: int, b_blocks: int, total_words: int, settings: Settings
) -> bool:
    return (
        a_blocks + b_blocks <= settings.inline_blocks_per_comparison
        and total_words <= settings.inline_tokens_per_comparison
    )


def _ensure_under_hard_ceiling(total_blocks: int, total_words: int, settings: Settings) -> None:
    if total_blocks > settings.max_blocks_per_comparison:
        raise ApiError(
            ErrorCode.DIFF_BUDGET_EXCEEDED,
            f"{total_blocks} blocks exceeds the {settings.max_blocks_per_comparison} limit.",
        )
    if total_words > settings.max_tokens_per_comparison:
        raise ApiError(
            ErrorCode.DIFF_BUDGET_EXCEEDED,
            f"{total_words} words exceeds the {settings.max_tokens_per_comparison} limit.",
        )


def _accepted(comparison: ComparisonResult, *, retry_after: int = 2) -> ComparisonAccepted:
    return ComparisonAccepted(
        comparison_id=comparison.comparison_id,
        created_at=comparison.created_at,
        expires_at=comparison.expires_at,
        retry_after=retry_after,
    )


def _window_if_needed(comparison: ComparisonResult, settings: Settings) -> ComparisonResult:
    total_blocks = comparison.total_blocks
    serialized_bytes = len(comparison.model_dump_json())
    if (
        total_blocks <= settings.comparison_window_block_threshold
        and serialized_bytes <= settings.comparison_window_serialized_bytes
    ):
        return comparison
    window = comparison.blocks[: settings.default_block_page_limit]
    return comparison.model_copy(
        update={"blocks": window, "truncated": True, "total_blocks": total_blocks}
    )


def _compute_background(
    *,
    comparison_id: str,
    a_document_id: str,
    b_document_id: str,
    payload: CreateComparisonRequest,
    settings: Settings,
    store: SessionStore,
    created_at: datetime,
) -> None:
    ttl = timedelta(hours=settings.comparison_ttl_hours)
    try:
        a_document = store.get_document(a_document_id)
        b_document = store.get_document(b_document_id)
        comparison = build_comparison(
            a_document,
            b_document,
            payload.options,
            ttl=ttl,
            comparison_id=comparison_id,
            created_at=created_at,
        )
        store.put_comparison(
            comparison,
            status=ComparisonStatus.COMPLETE.value,
            expires_at=comparison.expires_at,
        )
    except Exception as exc:
        store.mark_comparison_failed(comparison_id, str(exc))


@router.post(
    "",
    response_model=ComparisonResult | ComparisonAccepted,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_enforce_rate_limit)],
)
def create_comparison(
    payload: CreateComparisonRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: SessionStore = Depends(get_store),
) -> ComparisonResult | ComparisonAccepted:
    """Collate two witnesses.

    Small comparisons are computed inline and return ``201`` with the full
    result. Comparisons above the inline budget return ``202`` with a
    ``ComparisonAccepted`` body and are computed in the background; the client
    polls ``GET /comparisons/{id}`` until it reaches ``COMPLETE``.
    """
    _no_store(response)

    try:
        a_document = store.get_document(payload.a_document_id)
        b_document = store.get_document(payload.b_document_id)
    except DocumentNotFound as exc:
        raise ApiError(ErrorCode.DOCUMENT_NOT_FOUND, str(exc)) from exc

    a_blocks = len(a_document.blocks)
    b_blocks = len(b_document.blocks)
    total_blocks = a_blocks + b_blocks
    total_words = a_document.metadata.word_count + b_document.metadata.word_count
    _ensure_under_hard_ceiling(total_blocks, total_words, settings)

    ttl = timedelta(hours=settings.comparison_ttl_hours)
    created_at = datetime.now(UTC)
    expires_at = created_at + ttl

    if not _within_inline_budget(a_blocks, b_blocks, total_words, settings):
        comparison_id = new_comparison_id()
        pending = store.put_pending_comparison(
            comparison_id=comparison_id,
            a=a_document,
            b=b_document,
            options=payload.options,
            created_at=created_at,
            expires_at=expires_at,
        )
        background_tasks.add_task(
            _compute_background,
            comparison_id=comparison_id,
            a_document_id=payload.a_document_id,
            b_document_id=payload.b_document_id,
            payload=payload,
            settings=settings,
            store=store,
            created_at=created_at,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        response.headers["Retry-After"] = "2"
        return _accepted(pending)

    try:
        comparison = build_comparison(
            a_document,
            b_document,
            payload.options,
            ttl=ttl,
            created_at=created_at,
        )
    except DiffBudgetExceeded as exc:
        raise ApiError(ErrorCode.DIFF_BUDGET_EXCEEDED, str(exc)) from exc

    stored = store.put_comparison(
        comparison,
        status=ComparisonStatus.COMPLETE.value,
        expires_at=expires_at,
    )
    return _window_if_needed(stored, settings)


@router.get(
    "/{comparison_id}",
    response_model=ComparisonResult | ComparisonAccepted,
    dependencies=[Depends(_enforce_rate_limit)],
)
def get_comparison(
    comparison_id: str,
    response: Response,
    include_blocks: bool = Query(default=True),
    settings: Settings = Depends(get_settings),
    store: SessionStore = Depends(get_store),
) -> ComparisonResult | ComparisonAccepted:
    _no_store(response)
    try:
        record = store.get_comparison_record(comparison_id)
    except ComparisonExpired as exc:
        raise ApiError(
            ErrorCode.COMPARISON_EXPIRED,
            f"Comparison {comparison_id} has expired.",
        ) from exc
    except ComparisonNotFound as exc:
        raise ApiError(
            ErrorCode.COMPARISON_NOT_FOUND,
            f"No comparison with id {comparison_id}.",
        ) from exc

    if record.status == ComparisonStatus.PENDING.value:
        response.status_code = status.HTTP_202_ACCEPTED
        response.headers["Retry-After"] = "2"
        return _accepted(record.comparison)
    if record.status == ComparisonStatus.FAILED.value:
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            record.failure_detail or f"Comparison {comparison_id} failed.",
        )

    comparison = record.comparison

    if not include_blocks:
        # truncated tells the client the blocks array is a window rather than
        # the whole comparison, which is exactly the case here.
        return comparison.model_copy(update={"blocks": [], "truncated": True})

    return _window_if_needed(comparison, settings)


@router.get("/{comparison_id}/blocks", response_model=BlockPage)
def get_comparison_blocks(
    comparison_id: str,
    response: Response,
    offset: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1),
    settings: Settings = Depends(get_settings),
    store: SessionStore = Depends(get_store),
    _: None = Depends(_enforce_rate_limit),
) -> BlockPage:
    _no_store(response)
    resolved = min(limit or settings.default_block_page_limit, settings.max_block_page_limit)

    try:
        return store.get_comparison_blocks(comparison_id, offset, resolved)
    except ComparisonExpired as exc:
        raise ApiError(
            ErrorCode.COMPARISON_EXPIRED,
            f"Comparison {comparison_id} has expired.",
        ) from exc
    except ComparisonNotFound as exc:
        raise ApiError(
            ErrorCode.COMPARISON_NOT_FOUND,
            f"No comparison with id {comparison_id}.",
        ) from exc


@router.get(
    "/{comparison_id}/export/tei",
    response_class=Response,
    responses={
        200: {
            "content": {"application/tei+xml": {}},
            "description": "TEI P5 collation using the parallel segmentation method.",
        },
        202: {
            "model": ComparisonAccepted,
            "description": "Still being collated; poll and retry.",
        },
    },
    dependencies=[Depends(_enforce_rate_limit)],
)
def export_comparison_tei(
    comparison_id: str,
    store: SessionStore = Depends(get_store),
) -> Response:
    """Export the collation as a TEI P5 document.

    See ``docs/adr/0006-tei-parallel-segmentation-export.md``. The stored
    comparison is read whole rather than windowed: a partial collation
    serialised as a complete one would be a quietly wrong scholarly artifact,
    and unlike a truncated screen it carries no sign that anything is missing.
    """
    try:
        record = store.get_comparison_record(comparison_id)
    except ComparisonExpired as exc:
        raise ApiError(
            ErrorCode.COMPARISON_EXPIRED,
            f"Comparison {comparison_id} has expired.",
        ) from exc
    except ComparisonNotFound as exc:
        raise ApiError(
            ErrorCode.COMPARISON_NOT_FOUND,
            f"No comparison with id {comparison_id}.",
        ) from exc

    if record.status == ComparisonStatus.PENDING.value:
        # Exporting now would serialise a comparison with no blocks in it.
        accepted = JSONResponse(
            content=jsonable_encoder(_accepted(record.comparison)),
            status_code=status.HTTP_202_ACCEPTED,
            headers={"Retry-After": "2"},
        )
        _no_store(accepted)
        return accepted
    if record.status == ComparisonStatus.FAILED.value:
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            record.failure_detail or f"Comparison {comparison_id} failed.",
        )

    response = Response(
        content=build_tei(record.comparison),
        media_type="application/tei+xml",
        headers={
            # An attachment rather than inline: browsers render unfamiliar XML
            # as tag soup, and this is a file to keep, not a page to read.
            "Content-Disposition": f'attachment; filename="palimpsest-{comparison_id}.xml"',
        },
    )
    _no_store(response)
    return response


@router.delete(
    "/{comparison_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_enforce_rate_limit)],
)
def delete_comparison(
    comparison_id: str,
    store: SessionStore = Depends(get_store),
) -> None:
    store.delete_comparison(comparison_id)
