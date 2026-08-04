"""Payload assembly — the formatting service.

Turns alignments into ``DiffBlock`` objects and a ``ComparisonResult``. This
layer owns the wire shape so the diff engine never thinks about the UI.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.diff import (
    BlockStatus,
    ComparisonResult,
    DiffBlock,
    DiffOptions,
    Token,
    TokenStatus,
)
from app.models.document import Block, BlockKind, Document, DocumentSummary
from app.models.identifiers import diff_block_id, group_id, new_comparison_id
from app.services.diffing.alignment import Alignment, Relation, align
from app.services.diffing.engine import diff_tokens
from app.services.diffing.metrics import block_metrics, document_metrics


def _joined(blocks: list[Block], indices: tuple[int, ...]) -> str:
    return " ".join(blocks[i].text for i in indices)


def _status_for(alignment: Alignment, a_text: str, b_text: str) -> BlockStatus:
    match alignment.relation:
        case Relation.INSERTED:
            return BlockStatus.INSERTED
        case Relation.DELETED:
            return BlockStatus.DELETED
        case Relation.SPLIT:
            return BlockStatus.SPLIT
        case Relation.MERGED:
            return BlockStatus.MERGED
        case _:
            if alignment.move_distance is not None:
                # A block both moved and edited reports as MOVED: the
                # structural fact dominates, and the token metrics still carry
                # the edit counts so nothing is hidden.
                return BlockStatus.MOVED
            return BlockStatus.UNCHANGED if a_text == b_text else BlockStatus.MODIFIED


def _kind_for(alignment: Alignment, a_blocks: list[Block], b_blocks: list[Block]) -> BlockKind:
    if alignment.b_indices:
        return b_blocks[alignment.b_indices[0]].kind
    if alignment.a_indices:
        return a_blocks[alignment.a_indices[0]].kind
    return BlockKind.PARAGRAPH


def _split_run(token: Token, at: int) -> tuple[Token, Token]:
    """Cut one token's text at a character offset, preserving status."""
    return (
        Token(text=token.text[:at], status=token.status),
        Token(text=token.text[at:], status=token.status),
    )


def _distribute(
    tokens: list[Token], member_lengths: list[int], many_is_b: bool
) -> list[list[Token]]:
    """Partition a group's unified token stream across its members.

    The group is diffed once, as a whole, so that a pure re-paragraphing
    reports zero edits — the author changed the paragraphing and not one word,
    and diffing each member against the whole would manufacture a deletion and
    an insertion for every word that moved across the boundary.

    Tokens are then apportioned by walking the many-side text and cutting at
    each member's boundary. Tokens absent from the many side (deletions when
    the many side is B, insertions when it is A) attach to the member being
    built, so nothing is lost.
    """
    absent = TokenStatus.DELETION if many_is_b else TokenStatus.INSERTION

    members: list[list[Token]] = [[] for _ in member_lengths]
    if not member_lengths:
        return members

    index = 0
    consumed = 0
    remaining = list(tokens)

    while remaining:
        token = remaining.pop(0)

        if token.status is absent:
            members[index].append(token)
            continue

        capacity = member_lengths[index] - consumed
        if len(token.text) <= capacity or index == len(member_lengths) - 1:
            members[index].append(token)
            consumed += len(token.text)
        else:
            head, tail = _split_run(token, capacity)
            if head.text:
                members[index].append(head)
            remaining.insert(0, tail)
            consumed = member_lengths[index]

        while index < len(member_lengths) - 1 and consumed >= member_lengths[index]:
            consumed -= member_lengths[index]
            index += 1

    return members


def _group_blocks(
    alignment: Alignment,
    a_blocks: list[Block],
    b_blocks: list[Block],
    options: DiffOptions,
    status: BlockStatus,
    gid: str,
    next_sequence: int,
) -> list[DiffBlock]:
    """Emit one ``DiffBlock`` per member of a split or merge group.

    All members share a ``group_id`` so the client draws a single connector.
    """
    split = alignment.relation is Relation.SPLIT
    many_side = alignment.b_indices if split else alignment.a_indices
    many_blocks = b_blocks if split else a_blocks
    one_indices = alignment.a_indices if split else alignment.b_indices
    one_blocks = a_blocks if split else b_blocks

    one_text = _joined(one_blocks, one_indices)
    many_texts = [many_blocks[i].text for i in many_side]
    many_joined = " ".join(many_texts)

    a_text = one_text if split else many_joined
    b_text = many_joined if split else one_text
    tokens, _, _ = diff_tokens(a_text, b_text, options)

    # The joining space between members belongs to the preceding member.
    lengths = [len(text) + 1 for text in many_texts]
    lengths[-1] -= 1

    per_member = _distribute(tokens, lengths, many_is_b=split)

    emitted: list[DiffBlock] = []
    for position, member in enumerate(many_side):
        member_tokens = per_member[position]
        member_a = [t for t in member_tokens if t.status is not TokenStatus.INSERTION]
        member_b = [t for t in member_tokens if t.status is not TokenStatus.DELETION]

        if split:
            a_index, b_index = one_indices[0], member
            a_block_id = one_blocks[one_indices[0]].id
            b_block_id = many_blocks[member].id
        else:
            a_index, b_index = member, one_indices[0]
            a_block_id = many_blocks[member].id
            b_block_id = one_blocks[one_indices[0]].id

        a_joined = "".join(t.text for t in member_a)
        b_joined = "".join(t.text for t in member_b)

        emitted.append(
            DiffBlock(
                id=diff_block_id(next_sequence + position),
                status=status,
                kind=_kind_for(alignment, a_blocks, b_blocks),
                a_index=a_index,
                b_index=b_index,
                a_block_id=a_block_id,
                b_block_id=b_block_id,
                tokens=member_tokens,
                a_tokens=member_a,
                b_tokens=member_b,
                metrics=block_metrics(
                    member_tokens, a_joined, b_joined, status=BlockStatus.MODIFIED
                ),
                move_distance=None,
                group_id=gid,
            )
        )
    return emitted


def build_diff_blocks(
    a_document: Document,
    b_document: Document,
    options: DiffOptions | None = None,
) -> list[DiffBlock]:
    options = options or DiffOptions()
    a_blocks = a_document.blocks
    b_blocks = b_document.blocks

    alignments = align(a_blocks, b_blocks, options)

    blocks: list[DiffBlock] = []
    sequence = 1
    group_sequence = 0

    for alignment in alignments:
        if alignment.relation in (Relation.SPLIT, Relation.MERGED):
            group_sequence += 1
            members = _group_blocks(
                alignment,
                a_blocks,
                b_blocks,
                options,
                _status_for(alignment, "", ""),
                group_id(group_sequence),
                sequence,
            )
            blocks.extend(members)
            sequence += len(members)
            continue

        a_text = _joined(a_blocks, alignment.a_indices)
        b_text = _joined(b_blocks, alignment.b_indices)
        status = _status_for(alignment, a_text, b_text)

        tokens, a_tokens, b_tokens = diff_tokens(a_text, b_text, options)
        blocks.append(
            DiffBlock(
                id=diff_block_id(sequence),
                status=status,
                kind=_kind_for(alignment, a_blocks, b_blocks),
                a_index=alignment.a_index,
                b_index=alignment.b_index,
                a_block_id=(
                    a_blocks[alignment.a_index].id if alignment.a_index is not None else None
                ),
                b_block_id=(
                    b_blocks[alignment.b_index].id if alignment.b_index is not None else None
                ),
                tokens=tokens,
                a_tokens=a_tokens,
                b_tokens=b_tokens,
                metrics=block_metrics(tokens, a_text, b_text, status=status),
                move_distance=alignment.move_distance,
                group_id=None,
            )
        )
        sequence += 1

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
