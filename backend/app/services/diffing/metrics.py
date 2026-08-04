"""Metrics.

Every definition here is normative in docs/04-diff-engine.md. The client
formats these numbers and never computes them, which is what makes the
golden-corpus tests meaningful: they pin the entire user-visible result.

The counts are of **words**, never of ``Token`` objects — a ``Token`` carries a
contiguous run. This is the easiest thing in the schema to get wrong.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from app.models.diff import (
    BlockMetrics,
    BlockStatus,
    DiffBlock,
    DiffMetrics,
    Token,
    TokenStatus,
)


def _words(tokens: list[Token], status: TokenStatus | None = None) -> int:
    return sum(t.word_count() for t in tokens if status is None or t.status is status)


def similarity(a_text: str, b_text: str) -> float:
    """Normalized Indel similarity in ``0.0``-``1.0``.

    ``fuzz.ratio`` is deliberately order-sensitive. ``token_set_ratio`` and
    friends discard word order and would happily match a paragraph against its
    own scrambled rewrite, which is exactly the error this metric must not make.
    """
    if not a_text and not b_text:
        return 1.0
    return round(fuzz.ratio(a_text, b_text) / 100.0, 4)


def block_metrics(
    tokens: list[Token],
    a_text: str,
    b_text: str,
    *,
    status: BlockStatus,
) -> BlockMetrics:
    insertions = _words(tokens, TokenStatus.INSERTION)
    deletions = _words(tokens, TokenStatus.DELETION)
    edit_count = insertions + deletions

    # An inserted or deleted block has no counterpart, so similarity is 0.
    score = (
        0.0 if status in (BlockStatus.INSERTED, BlockStatus.DELETED) else similarity(a_text, b_text)
    )

    denominator = max(1, len(a_text.split()) + len(b_text.split()))

    return BlockMetrics(
        similarity=score,
        edit_count=edit_count,
        insertions=insertions,
        deletions=deletions,
        churn=round(edit_count / denominator, 4),
    )


def document_metrics(blocks: list[DiffBlock]) -> DiffMetrics:
    insertions = sum(b.metrics.insertions for b in blocks)
    deletions = sum(b.metrics.deletions for b in blocks)
    unchanged = sum(_words(b.tokens, TokenStatus.UNCHANGED) for b in blocks)
    edit_count = insertions + deletions

    a_word_count = sum(_words(b.a_tokens) for b in blocks)
    b_word_count = sum(_words(b.b_tokens) for b in blocks)
    total = a_word_count + b_word_count

    # A token-weighted Dice coefficient rather than a mean of block
    # similarities: averaging block scores would let a one-line heading count
    # as much as a thousand-word chapter.
    doc_similarity = round(2 * unchanged / total, 4) if total else 1.0

    return DiffMetrics(
        similarity=doc_similarity,
        edit_count=edit_count,
        insertions=insertions,
        deletions=deletions,
        unchanged_tokens=unchanged,
        churn=round(edit_count / total, 4) if total else 0.0,
        # Structural counts are reported separately and never folded into
        # edit_count: a re-paragraphing with no word changed must read as high
        # structural change and zero edits.
        blocks_moved=sum(1 for b in blocks if b.status is BlockStatus.MOVED),
        blocks_split=sum(1 for b in blocks if b.status is BlockStatus.SPLIT),
        blocks_merged=sum(1 for b in blocks if b.status is BlockStatus.MERGED),
        a_word_count=a_word_count,
        b_word_count=b_word_count,
    )
