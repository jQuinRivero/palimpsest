"""Payload assembly — the formatting service.

Turns aligned block pairs into ``DiffBlock`` objects and a ``ComparisonResult``.
This layer owns the wire shape so the diff engine never thinks about the UI.

Phase 1 aligns blocks positionally. Real alignment — exact-match anchoring,
gap-confined similarity search, split/merge detection and LIS move detection —
arrives in phase 3 and replaces ``_align_positionally`` only. Everything else
in this module is already the final shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.diff import (
    BlockStatus,
    ComparisonResult,
    DiffBlock,
    DiffOptions,
    Token,
)
from app.models.document import Block, Document, DocumentSummary
from app.models.identifiers import diff_block_id, new_comparison_id
from app.services.diffing.engine import diff_tokens
from app.services.diffing.metrics import block_metrics, document_metrics


def _pair_status(a: Block | None, b: Block | None, tokens: list[Token]) -> BlockStatus:
    if a is None:
        return BlockStatus.INSERTED
    if b is None:
        return BlockStatus.DELETED
    if a.text == b.text:
        return BlockStatus.UNCHANGED
    return BlockStatus.MODIFIED


def _align_positionally(
    a_blocks: list[Block], b_blocks: list[Block]
) -> list[tuple[Block | None, Block | None]]:
    """Phase-1 alignment: pair blocks by ordinal, then report the tail.

    This is deliberately naive and is the one piece of the diff pipeline that
    phase 3 replaces wholesale. It cannot detect a move, a split or a merge —
    which is precisely why docs/04-diff-engine.md treats alignment as the
    component carrying the real intelligence.
    """
    pairs: list[tuple[Block | None, Block | None]] = []
    shared = min(len(a_blocks), len(b_blocks))

    for index in range(shared):
        pairs.append((a_blocks[index], b_blocks[index]))
    for block in a_blocks[shared:]:
        pairs.append((block, None))
    for block in b_blocks[shared:]:
        pairs.append((None, block))

    return pairs


def build_diff_blocks(
    a_document: Document,
    b_document: Document,
    options: DiffOptions | None = None,
) -> list[DiffBlock]:
    options = options or DiffOptions()
    pairs = _align_positionally(a_document.blocks, b_document.blocks)

    blocks: list[DiffBlock] = []
    for sequence, (a_block, b_block) in enumerate(pairs, start=1):
        a_text = a_block.text if a_block else ""
        b_text = b_block.text if b_block else ""

        tokens, a_tokens, b_tokens = diff_tokens(a_text, b_text, options)
        status = _pair_status(a_block, b_block, tokens)

        blocks.append(
            DiffBlock(
                id=diff_block_id(sequence),
                status=status,
                # An inserted block has no A counterpart, so its kind comes
                # from B, and vice versa.
                kind=(b_block or a_block).kind,  # type: ignore[union-attr]
                a_index=a_block.index if a_block else None,
                b_index=b_block.index if b_block else None,
                a_block_id=a_block.id if a_block else None,
                b_block_id=b_block.id if b_block else None,
                tokens=tokens,
                a_tokens=a_tokens,
                b_tokens=b_tokens,
                metrics=block_metrics(tokens, a_text, b_text, status=status),
                move_distance=None,
                group_id=None,
            )
        )

    return blocks


def build_comparison(
    a_document: Document,
    b_document: Document,
    options: DiffOptions | None = None,
    *,
    ttl: timedelta = timedelta(days=7),
    comparison_id: str | None = None,
    created_at: datetime | None = None,
) -> ComparisonResult:
    """Assemble the complete payload for two witnesses."""
    options = options or DiffOptions()
    blocks = build_diff_blocks(a_document, b_document, options)
    created = created_at or datetime.now(UTC)

    return ComparisonResult(
        comparison_id=comparison_id or new_comparison_id(),
        created_at=created,
        expires_at=created + ttl,
        a=DocumentSummary.from_document(a_document),
        b=DocumentSummary.from_document(b_document),
        blocks=blocks,
        metrics=document_metrics(blocks),
        options=options,
        truncated=False,
        total_blocks=len(blocks),
    )
