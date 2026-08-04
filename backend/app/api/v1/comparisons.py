"""Comparison creation and retrieval."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import get_store
from app.api.errors import ApiError
from app.config import Settings, get_settings
from app.models.api import ComparisonStatus, CreateComparisonRequest, ErrorCode
from app.models.diff import BlockPage, ComparisonResult
from app.services.diffing.engine import DiffBudgetExceeded
from app.services.formatting.payload import build_comparison
from app.storage.store import (
    ComparisonExpired,
    ComparisonNotFound,
    DocumentNotFound,
    SessionStore,
)

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


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


@router.post("", response_model=ComparisonResult, status_code=status.HTTP_201_CREATED)
def create_comparison(
    payload: CreateComparisonRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
    store: SessionStore = Depends(get_store),
) -> ComparisonResult:
    """Collate two witnesses.

    Phase 1 always computes inline and returns ``201``. The ``202
    ComparisonAccepted`` path for oversize manuscripts is phase 5; the response
    model already exists so enabling it is a routing change, not a schema
    change.
    """
    _no_store(response)

    try:
        a_document = store.get_document(payload.a_document_id)
        b_document = store.get_document(payload.b_document_id)
    except DocumentNotFound as exc:
        raise ApiError(ErrorCode.DOCUMENT_NOT_FOUND, str(exc)) from exc

    total_blocks = len(a_document.blocks) + len(b_document.blocks)
    if total_blocks > settings.max_blocks_per_comparison:
        raise ApiError(
            ErrorCode.DIFF_BUDGET_EXCEEDED,
            f"{total_blocks} blocks exceeds the {settings.max_blocks_per_comparison} limit.",
        )

    total_words = a_document.metadata.word_count + b_document.metadata.word_count
    if total_words > settings.max_tokens_per_comparison:
        raise ApiError(
            ErrorCode.DIFF_BUDGET_EXCEEDED,
            f"{total_words} words exceeds the {settings.max_tokens_per_comparison} limit.",
        )

    ttl = timedelta(hours=settings.comparison_ttl_hours)
    try:
        comparison = build_comparison(a_document, b_document, payload.options, ttl=ttl)
    except DiffBudgetExceeded as exc:
        raise ApiError(ErrorCode.DIFF_BUDGET_EXCEEDED, str(exc)) from exc

    return store.put_comparison(
        comparison,
        status=ComparisonStatus.COMPLETE.value,
        expires_at=datetime.now(UTC) + ttl,
    )


@router.get("/{comparison_id}", response_model=ComparisonResult)
def get_comparison(
    comparison_id: str,
    response: Response,
    include_blocks: bool = Query(default=True),
    store: SessionStore = Depends(get_store),
) -> ComparisonResult:
    _no_store(response)
    comparison = _load(store, comparison_id)

    if not include_blocks:
        # truncated tells the client the blocks array is a window rather than
        # the whole comparison, which is exactly the case here.
        return comparison.model_copy(update={"blocks": [], "truncated": True})

    return comparison


@router.get("/{comparison_id}/blocks", response_model=BlockPage)
def get_comparison_blocks(
    comparison_id: str,
    response: Response,
    offset: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1),
    settings: Settings = Depends(get_settings),
    store: SessionStore = Depends(get_store),
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


@router.delete("/{comparison_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comparison(
    comparison_id: str,
    store: SessionStore = Depends(get_store),
) -> None:
    store.delete_comparison(comparison_id)
