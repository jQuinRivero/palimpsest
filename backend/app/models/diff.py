"""Diff models — the wire contract between the diff engine and every consumer.

See docs/05-data-schema.md, which is normative. The eight invariants it declares
are implemented as executable assertions in ``app.models.invariants``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.models.document import BlockKind, DocumentSummary


class TokenStatus(StrEnum):
    """What happened to a run of words.

    This enum is closed and will not grow. A token either survived, arrived, or
    left; anything richer belongs at block level. Keeping it closed is what
    allows the client's ``TokenSpan`` to stay trivially fast when a page holds
    tens of thousands of them.
    """

    UNCHANGED = "UNCHANGED"
    INSERTION = "INSERTION"
    DELETION = "DELETION"


class BlockStatus(StrEnum):
    """How a block relates to its counterpart in the other witness."""

    #: Aligned pair, byte-identical after normalization.
    UNCHANGED = "UNCHANGED"
    #: Aligned pair with differing tokens.
    MODIFIED = "MODIFIED"
    #: Present only in Manuscript B.
    INSERTED = "INSERTED"
    #: Present only in Manuscript A.
    DELETED = "DELETED"
    #: Aligned pair lying outside the longest increasing subsequence.
    MOVED = "MOVED"
    #: One A block became several B blocks.
    SPLIT = "SPLIT"
    #: Several A blocks became one B block.
    MERGED = "MERGED"


class Granularity(StrEnum):
    WORD = "WORD"
    CHARACTER = "CHARACTER"


class Token(BaseModel):
    """A contiguous run of same-status words.

    Note this is a *run*, not a single word: ``{"text": "cat sat ", ...}`` is
    two words in one object. Emitting one object per word would triple the
    payload and produce one DOM node per word for no reader-visible benefit.

    The consequence, which is the easiest thing in this schema to get wrong:
    every count in ``BlockMetrics`` and ``DiffMetrics`` is a count of **words**,
    never a count of ``Token`` objects.
    """

    #: Surface form, including trailing whitespace, so that concatenating a
    #: stream reproduces the source text exactly.
    text: str
    status: TokenStatus

    def word_count(self) -> int:
        return len(self.text.split())


class BlockMetrics(BaseModel):
    similarity: float
    edit_count: int
    insertions: int
    deletions: int
    churn: float


class DiffBlock(BaseModel):
    """One block of the collation, carrying all three token streams.

    Response-shaped: every field is always emitted, so none carry defaults.
    A field with a default is *not required* in the generated OpenAPI schema,
    which would force every client to null-check values that are in fact
    always present.
    """

    id: str
    status: BlockStatus
    kind: BlockKind
    #: Null if and only if status is INSERTED.
    a_index: int | None
    #: Null if and only if status is DELETED.
    b_index: int | None
    a_block_id: str | None
    b_block_id: str | None
    #: Unified stream: UNCHANGED, INSERTION and DELETION interleaved.
    tokens: list[Token]
    #: Manuscript A pane: UNCHANGED + DELETION only.
    a_tokens: list[Token]
    #: Manuscript B pane: UNCHANGED + INSERTION only.
    b_tokens: list[Token]
    metrics: BlockMetrics
    #: Signed block displacement. Non-null if and only if status is MOVED.
    move_distance: int | None
    #: Shared by every member of a SPLIT or MERGED group.
    group_id: str | None


class DiffMetrics(BaseModel):
    similarity: float
    edit_count: int
    insertions: int
    deletions: int
    unchanged_tokens: int
    churn: float
    blocks_moved: int
    blocks_split: int
    blocks_merged: int
    a_word_count: int
    b_word_count: int


class DiffOptions(BaseModel):
    granularity: Granularity = Granularity.WORD
    detect_moves: bool = True
    #: Minimum similarity for two blocks to be considered a pair.
    align_threshold: float = 0.50
    #: Minimum similarity before a displaced pair is reported as MOVED.
    #: Deliberately higher than align_threshold: repetitive text such as verse
    #: refrains produces legitimate near-matches, and a weak pair should not
    #: have its displacement reported as an authorial move.
    move_threshold: float = 0.75
    ignore_case: bool = False
    ignore_punctuation: bool = False
    normalize_whitespace: bool = True


class ComparisonResult(BaseModel):
    """The complete collation of two witnesses."""

    comparison_id: str
    created_at: datetime
    expires_at: datetime
    a: DocumentSummary
    b: DocumentSummary
    #: In reading order. Clients render as given and must never re-sort.
    blocks: list[DiffBlock]
    metrics: DiffMetrics
    options: DiffOptions
    #: True when ``blocks`` is a window rather than the whole comparison.
    truncated: bool
    total_blocks: int


class BlockPage(BaseModel):
    """A window into a comparison's blocks, for very long manuscripts."""

    blocks: list[DiffBlock]
    offset: int
    limit: int
    total_blocks: int
