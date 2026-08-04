"""The eight payload invariants from docs/05-data-schema.md, as executable checks.

The specification declares these in prose and the session validator checked them
against the JSON examples in the docs. This module is the same logic applied to
what the engine actually produces, so the spec's examples and the real
implementation are judged by identical rules.

Every engine and formatting test asserts against ``check_comparison``. A failure
here is a contract violation, not a style problem.
"""

from __future__ import annotations

import unicodedata

from app.models.diff import (
    BlockStatus,
    ComparisonResult,
    DiffBlock,
    DiffOptions,
    Token,
    TokenStatus,
)


class InvariantViolation(AssertionError):
    """A payload broke the contract in docs/05-data-schema.md."""


def _words(tokens: list[Token]) -> int:
    return sum(token.word_count() for token in tokens)


def _text(tokens: list[Token]) -> str:
    return "".join(token.text for token in tokens)


def _fold(text: str, options: DiffOptions) -> list[str]:
    """Reduce text to the word sequence the engine treated as significant.

    Mirrors ``app.services.diffing.tokenizer.comparison_key``. Kept local so
    the model layer does not import from the service layer, but the two must
    agree; ``tests/unit/test_diff_engine.py`` asserts they do.
    """
    words = text.split()
    if options.ignore_case:
        words = [w.casefold() for w in words]
    if options.ignore_punctuation:
        words = [
            "".join(ch for ch in w if not unicodedata.category(ch).startswith("P")) for w in words
        ]
    return [w for w in words if w]


def check_block(block: DiffBlock, *, options: DiffOptions | None = None) -> list[str]:
    """Return a list of invariant violations for one ``DiffBlock``.

    Invariant 1 as stated in the specification bundles two guarantees that are
    not equally strong, so this implementation separates them.

    **Exact, always.** ``a_tokens`` reproduces Manuscript A's block text
    character for character, and ``b_tokens`` reproduces Manuscript B's. That
    is the guarantee that makes the payload lossless, and it is asserted by
    ``assert_reconstructs``.

    **Word-for-word.** The unified ``tokens`` stream, filtered of insertions,
    agrees with ``a_tokens`` on the word sequence; filtered of deletions, with
    ``b_tokens``. It is *not* required to agree on whitespace, for two
    reasons. The unified stream interleaves runs that were never adjacent in
    either witness and must insert separators so words cannot fuse
    ("alpha" + "beta" would otherwise read "alphabeta"). And under
    ``normalize_whitespace`` — on by default — two runs compare equal while
    carrying different trailing whitespace, because a word ending a block in
    one witness sits mid-block in the other.

    Under ``ignore_case`` or ``ignore_punctuation`` the word comparison is
    folded the same way the engine folded it, so the check asserts exactly the
    equivalence the engine claimed.
    """
    options = options or DiffOptions()
    errors: list[str] = []
    ref = f"block {block.id}"

    # Invariant 2 — stream purity.
    if any(t.status is TokenStatus.INSERTION for t in block.a_tokens):
        errors.append(f"{ref}: a_tokens contains an INSERTION")
    if any(t.status is TokenStatus.DELETION for t in block.b_tokens):
        errors.append(f"{ref}: b_tokens contains a DELETION")

    # Invariant 1 — applied symmetrically to both panes.
    derived = {
        "a_tokens": _text([t for t in block.tokens if t.status is not TokenStatus.INSERTION]),
        "b_tokens": _text([t for t in block.tokens if t.status is not TokenStatus.DELETION]),
    }
    actual = {"a_tokens": _text(block.a_tokens), "b_tokens": _text(block.b_tokens)}

    for pane, from_unified in derived.items():
        pane_text = actual[pane]
        if _fold(from_unified, options) != _fold(pane_text, options):
            errors.append(
                f"{ref}: unified stream word sequence diverges from {pane} "
                f"({from_unified!r} vs {pane_text!r})"
            )

    # Invariant 3 — metric arithmetic.
    m = block.metrics
    if m.edit_count != m.insertions + m.deletions:
        errors.append(
            f"{ref}: edit_count {m.edit_count} != insertions {m.insertions} "
            f"+ deletions {m.deletions}"
        )

    # Counts are of words, not of Token objects.
    counted_insertions = _words([t for t in block.tokens if t.status is TokenStatus.INSERTION])
    counted_deletions = _words([t for t in block.tokens if t.status is TokenStatus.DELETION])
    if m.insertions != counted_insertions:
        errors.append(f"{ref}: insertions {m.insertions} != {counted_insertions} counted words")
    if m.deletions != counted_deletions:
        errors.append(f"{ref}: deletions {m.deletions} != {counted_deletions} counted words")

    # Invariants 4, 5, 6 — null-field rules.
    if (block.a_index is None) != (block.status is BlockStatus.INSERTED):
        errors.append(f"{ref}: a_index is null iff INSERTED violated (status={block.status})")
    if (block.b_index is None) != (block.status is BlockStatus.DELETED):
        errors.append(f"{ref}: b_index is null iff DELETED violated (status={block.status})")
    if (block.move_distance is not None) != (block.status is BlockStatus.MOVED):
        errors.append(f"{ref}: move_distance is non-null iff MOVED violated")
    if (block.group_id is not None) != (block.status in (BlockStatus.SPLIT, BlockStatus.MERGED)):
        errors.append(f"{ref}: group_id is non-null iff SPLIT/MERGED violated")

    return errors


def check_comparison(result: ComparisonResult) -> list[str]:
    """Return a list of invariant violations for a whole ``ComparisonResult``."""
    errors: list[str] = []

    for block in result.blocks:
        errors.extend(check_block(block, options=result.options))

    # Invariant 6 (continued) — every member of a group shares one id.
    groups: dict[str, list[BlockStatus]] = {}
    for block in result.blocks:
        if block.group_id is not None:
            groups.setdefault(block.group_id, []).append(block.status)
    for group_id, statuses in groups.items():
        if len(set(statuses)) > 1:
            errors.append(f"group {group_id}: mixed statuses {sorted(set(statuses))}")

    # Invariant 8 — a complete payload declares its own length honestly.
    if not result.truncated and len(result.blocks) != result.total_blocks:
        errors.append(
            f"truncated is false but len(blocks) {len(result.blocks)} "
            f"!= total_blocks {result.total_blocks}"
        )

    m = result.metrics
    if m.edit_count != m.insertions + m.deletions:
        errors.append("document edit_count != insertions + deletions")

    # Aggregate checks only make sense on a complete payload.
    if result.truncated or len(result.blocks) != result.total_blocks:
        return errors

    summed_insertions = sum(b.metrics.insertions for b in result.blocks)
    summed_deletions = sum(b.metrics.deletions for b in result.blocks)
    summed_unchanged = sum(
        _words([t for t in b.tokens if t.status is TokenStatus.UNCHANGED]) for b in result.blocks
    )
    if m.insertions != summed_insertions:
        errors.append(f"document insertions {m.insertions} != summed {summed_insertions}")
    if m.deletions != summed_deletions:
        errors.append(f"document deletions {m.deletions} != summed {summed_deletions}")
    if m.unchanged_tokens != summed_unchanged:
        errors.append(
            f"document unchanged_tokens {m.unchanged_tokens} != summed {summed_unchanged}"
        )

    a_words = sum(_words(b.a_tokens) for b in result.blocks)
    b_words = sum(_words(b.b_tokens) for b in result.blocks)
    if m.a_word_count != a_words:
        errors.append(f"a_word_count {m.a_word_count} != reconstructed {a_words}")
    if m.b_word_count != b_words:
        errors.append(f"b_word_count {m.b_word_count} != reconstructed {b_words}")

    total = m.a_word_count + m.b_word_count
    if total:
        expected_similarity = round(2 * m.unchanged_tokens / total, 4)
        if abs(expected_similarity - m.similarity) > 0.0002:
            errors.append(f"document similarity {m.similarity} != Dice {expected_similarity}")
        expected_churn = round(m.edit_count / total, 4)
        if abs(expected_churn - m.churn) > 0.0002:
            errors.append(f"document churn {m.churn} != {expected_churn}")

    for field, status in (
        ("blocks_moved", BlockStatus.MOVED),
        ("blocks_split", BlockStatus.SPLIT),
        ("blocks_merged", BlockStatus.MERGED),
    ):
        counted = sum(1 for b in result.blocks if b.status is status)
        if getattr(m, field) != counted:
            errors.append(f"{field} {getattr(m, field)} != counted {counted}")

    return errors


def assert_comparison(result: ComparisonResult) -> None:
    """Raise ``InvariantViolation`` if the payload breaks its contract."""
    errors = check_comparison(result)
    if errors:
        raise InvariantViolation(f"{len(errors)} invariant violation(s):\n  " + "\n  ".join(errors))


def assert_reconstructs(
    block: DiffBlock, a_text: str | None = None, b_text: str | None = None
) -> None:
    """Assert the token streams reproduce the original block text.

    The cheapest high-value property in the system: if this holds, the diff
    neither invented nor lost a character.
    """
    if a_text is not None and _text(block.a_tokens) != a_text:
        raise InvariantViolation(
            f"block {block.id}: a_tokens reconstructs {_text(block.a_tokens)!r}, "
            f"expected {a_text!r}"
        )
    if b_text is not None and _text(block.b_tokens) != b_text:
        raise InvariantViolation(
            f"block {block.id}: b_tokens reconstructs {_text(block.b_tokens)!r}, "
            f"expected {b_text!r}"
        )
