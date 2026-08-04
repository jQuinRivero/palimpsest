"""Stage 1 of the diff engine: block alignment.

A linear diff reports a paragraph moved from chapter two to chapter nine as a
large deletion followed, thousands of tokens later, by a large insertion. That
is true, and useless: the scholar learns nothing about how the text evolved.
The same failure appears at smaller scale — split a paragraph and a linear diff
sees a deletion and two insertions; re-paragraph a chapter without changing a
word and it reports a total rewrite.

Alignment establishes which block in Manuscript A corresponds to which in
Manuscript B *before* any token diffing, so those relationships can be named.
This is the part of the system that is genuinely ours; token diffing is a
proven library doing what it is good at.

The pipeline is ordered so that the expensive step sees as few candidate pairs
as possible. Naive all-pairs similarity over a 100,000-word manuscript is
roughly 2,000 x 2,000 = four million comparisons; anchoring on exact matches
typically resolves most of the document for free and collapses the rest into
small independent sub-problems.

See docs/04-diff-engine.md.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum

from rapidfuzz import fuzz, process

from app.models.diff import DiffOptions
from app.models.document import Block

#: A candidate pair whose token counts differ by more than this ratio cannot
#: plausibly be a revision of one another. Rejecting on an integer comparison
#: is far cheaper than letting a string metric reach the same conclusion.
LENGTH_RATIO_LIMIT = 3.0

#: A concatenation must beat the best individual member by this margin before a
#: split is declared. Without it, a paragraph that already matches well on its
#: own would drag an unrelated neighbour into a spurious group.
SPLIT_MARGIN = 0.15

#: How many consecutive unmatched blocks may be considered as one split group.
#: Bounded because the concatenation test is quadratic in this window.
MAX_GROUP_SPAN = 4


class Relation(StrEnum):
    """How an aligned pair or group is related."""

    MATCHED = "MATCHED"
    SPLIT = "SPLIT"
    MERGED = "MERGED"
    INSERTED = "INSERTED"
    DELETED = "DELETED"


@dataclass(frozen=True, slots=True)
class Alignment:
    """One correspondence between Manuscript A and Manuscript B.

    A ``MATCHED`` alignment holds exactly one index on each side. ``SPLIT``
    holds one A index and several B indices; ``MERGED`` the reverse.
    ``INSERTED`` and ``DELETED`` hold indices on one side only.
    """

    relation: Relation
    a_indices: tuple[int, ...]
    b_indices: tuple[int, ...]
    similarity: float = 0.0
    #: Signed displacement in block ordinals, set only for a moved pair.
    move_distance: int | None = None

    @property
    def a_index(self) -> int | None:
        return self.a_indices[0] if self.a_indices else None

    @property
    def b_index(self) -> int | None:
        return self.b_indices[0] if self.b_indices else None


@dataclass
class _Gap:
    """A run of unmatched blocks between two anchors, on both sides."""

    a: list[int] = field(default_factory=list)
    b: list[int] = field(default_factory=list)


def similarity(a_text: str, b_text: str) -> float:
    """Normalized Indel similarity in ``0.0``-``1.0``.

    ``fuzz.ratio`` is order-sensitive by design. ``token_set_ratio`` and its
    relatives discard word order and would happily match a paragraph against
    its own scrambled rewrite, which is precisely the judgement this must not
    make.
    """
    if not a_text and not b_text:
        return 1.0
    if not a_text or not b_text:
        return 0.0
    return round(fuzz.ratio(a_text, b_text) / 100.0, 4)


def _plausible_length(a: Block, b: Block) -> bool:
    a_words = max(1, len(a.text.split()))
    b_words = max(1, len(b.text.split()))
    ratio = max(a_words, b_words) / min(a_words, b_words)
    return ratio <= LENGTH_RATIO_LIMIT


def _anchor(a_blocks: list[Block], b_blocks: list[Block]) -> list[tuple[int, int]]:
    """Pair blocks whose normalized text is identical and unique on both sides.

    In a realistic revision most blocks are untouched, so this resolves the
    bulk of the document at hash cost and pins the sequence. Ambiguous
    duplicates — a repeated refrain, a recurring stage direction — are
    deliberately left to the scoring stage, which has ordering context to
    disambiguate them.

    Every unique exact match is returned, including ones that are out of
    sequence. Filtering those out here would discard precisely the blocks that
    were moved and left otherwise untouched, which is the clearest case move
    detection exists to report.
    """
    a_counts = Counter(block.text for block in a_blocks)
    b_counts = Counter(block.text for block in b_blocks)

    b_by_text = {
        block.text: index for index, block in enumerate(b_blocks) if b_counts[block.text] == 1
    }

    anchors: list[tuple[int, int]] = []
    for a_index, block in enumerate(a_blocks):
        if a_counts[block.text] != 1:
            continue
        b_index = b_by_text.get(block.text)
        if b_index is not None:
            anchors.append((a_index, b_index))

    return anchors


def _longest_increasing_pairs(pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Keep the largest subset whose B ordinals increase with their A ordinals."""
    if not pairs:
        return []
    ordered = sorted(pairs)
    keep = longest_increasing_subsequence([b for _, b in ordered])
    return [ordered[i] for i in sorted(keep)]


def longest_increasing_subsequence(values: list[int]) -> set[int]:
    """Return the *positions* forming a longest strictly increasing subsequence.

    Positions outside the result are the minimal set whose displacement
    explains the reordering — which is exactly what move detection needs. A
    naive neighbour comparison would instead flag a whole chapter as moved when
    one paragraph was lifted out of it.
    """
    if not values:
        return set()

    import bisect

    tails: list[int] = []
    tail_positions: list[int] = []
    previous: list[int] = [-1] * len(values)

    for position, value in enumerate(values):
        slot = bisect.bisect_left(tails, value)
        if slot == len(tails):
            tails.append(value)
            tail_positions.append(position)
        else:
            tails[slot] = value
            tail_positions[slot] = position
        previous[position] = tail_positions[slot - 1] if slot else -1

    result: set[int] = set()
    cursor = tail_positions[-1] if tail_positions else -1
    while cursor != -1:
        result.add(cursor)
        cursor = previous[cursor]
    return result


def _gaps(
    anchors: list[tuple[int, int]],
    a_count: int,
    b_count: int,
    anchored_a: set[int],
    anchored_b: set[int],
) -> list[_Gap]:
    """Partition both witnesses into the unmatched regions between anchors.

    This is what turns one quadratic problem into a series of small independent
    ones. An unmatched A block lying between anchors *i* and *j* can only
    sensibly align with an unmatched B block lying between the same two.

    Only the monotonic anchors define boundaries — a moved anchor sits out of
    sequence and would carve the document into overlapping regions — but every
    anchored block is excluded from the gaps regardless, since it is already
    matched.
    """
    boundaries = _longest_increasing_pairs(anchors)

    gaps: list[_Gap] = []
    a_cursor = 0
    b_cursor = 0

    for a_index, b_index in [*boundaries, (a_count, b_count)]:
        gap = _Gap(
            a=[i for i in range(a_cursor, a_index) if i not in anchored_a],
            b=[i for i in range(b_cursor, b_index) if i not in anchored_b],
        )
        if gap.a or gap.b:
            gaps.append(gap)
        a_cursor = a_index + 1
        b_cursor = b_index + 1

    return gaps


def _score_gap(
    gap: _Gap,
    a_blocks: list[Block],
    b_blocks: list[Block],
    threshold: float,
) -> list[tuple[float, int, int]]:
    """Score plausible pairs within one gap, cheapest filters first.

    ``process.extract`` rather than ``process.cdist``: both score in C++ and
    discard sub-threshold results there, which is the property that matters,
    but ``cdist`` returns a numpy matrix and would pull numpy into a text tool
    for a single call. Gaps are small by construction after anchoring, so
    querying per block costs nothing measurable.
    """
    if not gap.a or not gap.b:
        return []

    b_texts = [b_blocks[i].text for i in gap.b]
    scored: list[tuple[float, int, int]] = []

    for a_index in gap.a:
        matches = process.extract(
            a_blocks[a_index].text,
            b_texts,
            scorer=fuzz.ratio,
            score_cutoff=threshold * 100,
            limit=None,
        )
        for _, raw, position in matches:
            b_index = gap.b[position]
            if not _plausible_length(a_blocks[a_index], b_blocks[b_index]):
                continue
            scored.append((round(float(raw) / 100.0, 4), a_index, b_index))

    return scored


def _assign(scored: list[tuple[float, int, int]], threshold: float) -> list[tuple[int, int, float]]:
    """Greedy best-first assignment.

    Optimal assignment via the Hungarian algorithm is deliberately not used.
    Gap sub-problems are small, greedy and optimal agree on almost all of them,
    and greedy is explicable: when a scholar asks why two paragraphs were
    paired, "they were each other's best remaining candidate at 0.83" is an
    answer, whereas a global optimum over a cost matrix is not.

    Ties break on the lower A ordinal, then the lower B ordinal, never
    arbitrarily — determinism is a hard requirement of the golden-corpus suite.
    """
    ordered = sorted(scored, key=lambda item: (-item[0], item[1], item[2]))

    taken_a: set[int] = set()
    taken_b: set[int] = set()
    pairs: list[tuple[int, int, float]] = []

    for score, a_index, b_index in ordered:
        if score < threshold:
            break
        if a_index in taken_a or b_index in taken_b:
            continue
        taken_a.add(a_index)
        taken_b.add(b_index)
        pairs.append((a_index, b_index, score))

    return pairs


def _runs(indices: list[int]) -> list[list[int]]:
    """Group sorted indices into runs of consecutive values."""
    runs: list[list[int]] = []
    for index in sorted(indices):
        if runs and index == runs[-1][-1] + 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    return runs


def _promote_groups(
    pairs: list[tuple[int, int, float]],
    unmatched_many: list[int],
    text_one: list[Block],
    text_many: list[Block],
    threshold: float,
) -> list[tuple[int, tuple[int, ...], float]]:
    """Promote a matched pair to a group when the concatenation is clearly better.

    Greedy assignment pairs a split paragraph with whichever half it resembles
    most, which consumes it before any concatenation test can run. So the test
    is applied *after* assignment: extend the matched B block with adjacent
    unmatched B blocks and see whether the joined text beats the pair's own
    score by ``SPLIT_MARGIN``.

    Without that margin a paragraph that already matches well on its own would
    drag an unrelated neighbour into a spurious group.
    """
    available = set(unmatched_many)
    promoted: list[tuple[int, tuple[int, ...], float]] = []

    for one_index, many_index, score in sorted(pairs, key=lambda p: p[0]):
        best: tuple[float, tuple[int, ...]] | None = None

        for before in range(MAX_GROUP_SPAN):
            for after in range(MAX_GROUP_SPAN):
                if before + after == 0:
                    continue
                window = list(range(many_index - before, many_index + after + 1))
                if len(window) > MAX_GROUP_SPAN:
                    continue
                extras = [i for i in window if i != many_index]
                if not all(i in available for i in extras):
                    continue
                if window[0] < 0 or window[-1] >= len(text_many):
                    continue

                joined = " ".join(text_many[i].text for i in window)
                combined = similarity(text_one[one_index].text, joined)
                if combined < threshold or combined <= score + SPLIT_MARGIN:
                    continue
                if best is None or combined > best[0]:
                    best = (combined, tuple(window))

        if best is not None:
            promoted.append((one_index, best[1], best[0]))
            available.difference_update(best[1])

    return promoted


def _detect_groups(
    unmatched_one: list[int],
    unmatched_many: list[int],
    text_one: list[Block],
    text_many: list[Block],
    threshold: float,
) -> list[tuple[int, tuple[int, ...], float]]:
    """Detect one-to-many correspondences among blocks nothing else claimed.

    A split is invisible to pairwise matching: if A's block 12 became B's
    blocks 12 and 13, each pair scores roughly half of what a match needs and
    both may fall below threshold, so the engine would report one deletion and
    two insertions — exactly the failure alignment exists to prevent.

    The test is on the *concatenation*, and it must both clear the threshold
    and beat the best individual member by ``SPLIT_MARGIN``.
    """
    groups: list[tuple[int, tuple[int, ...], float]] = []
    consumed: set[int] = set()

    for one_index in sorted(unmatched_one):
        best: tuple[float, tuple[int, ...]] | None = None

        for run in _runs([i for i in unmatched_many if i not in consumed]):
            for start in range(len(run)):
                for span in range(2, MAX_GROUP_SPAN + 1):
                    window = run[start : start + span]
                    if len(window) < 2:
                        continue

                    joined = " ".join(text_many[i].text for i in window)
                    combined = similarity(text_one[one_index].text, joined)
                    if combined < threshold:
                        continue

                    best_individual = max(
                        similarity(text_one[one_index].text, text_many[i].text) for i in window
                    )
                    if combined <= best_individual + SPLIT_MARGIN:
                        continue

                    if best is None or combined > best[0]:
                        best = (combined, tuple(window))

        if best is not None:
            groups.append((one_index, best[1], best[0]))
            consumed.update(best[1])

    return groups


def align(
    a_blocks: list[Block],
    b_blocks: list[Block],
    options: DiffOptions | None = None,
) -> list[Alignment]:
    """Establish correspondence between two witnesses.

    Returns alignments in reading order — Manuscript B's order, since B is the
    later state of the text and the reader is following its shape, with deleted
    material interleaved where its A neighbours imply.
    """
    options = options or DiffOptions()
    threshold = options.align_threshold

    anchors = _anchor(a_blocks, b_blocks)
    anchor_pairs = {(a, b) for a, b in anchors}
    anchored_a = {a for a, _ in anchors}
    anchored_b = {b for _, b in anchors}

    pairs: list[tuple[int, int, float]] = [(a, b, 1.0) for a, b in anchors]

    for gap in _gaps(anchors, len(a_blocks), len(b_blocks), anchored_a, anchored_b):
        scored = _score_gap(gap, a_blocks, b_blocks, threshold)
        pairs.extend(_assign(scored, threshold))

    matched_a = {a for a, _, _ in pairs}
    matched_b = {b for _, b, _ in pairs}

    unmatched_a = [i for i in range(len(a_blocks)) if i not in matched_a]
    unmatched_b = [i for i in range(len(b_blocks)) if i not in matched_b]

    # A split whose halves were consumed by pairwise matching is only
    # recoverable by re-examining the matched pairs, so that runs first.
    splits = _promote_groups(pairs, unmatched_b, a_blocks, b_blocks, threshold)
    promoted_a = {a for a, _, _ in splits}
    pairs = [p for p in pairs if p[0] not in promoted_a]
    for a_index, b_window, _ in splits:
        matched_a.add(a_index)
        matched_b.update(b_window)

    unmatched_b = [i for i in range(len(b_blocks)) if i not in matched_b]
    merges = _promote_groups(
        [(b, a, s) for a, b, s in pairs], unmatched_a, b_blocks, a_blocks, threshold
    )
    promoted_b = {b for b, _, _ in merges}
    pairs = [p for p in pairs if p[1] not in promoted_b]
    for b_index, a_window, _ in merges:
        matched_b.add(b_index)
        matched_a.update(a_window)

    # Then the case where nothing claimed either side.
    unmatched_a = [i for i in range(len(a_blocks)) if i not in matched_a]
    unmatched_b = [i for i in range(len(b_blocks)) if i not in matched_b]

    orphan_splits = _detect_groups(unmatched_a, unmatched_b, a_blocks, b_blocks, threshold)
    for a_index, b_window, _score in orphan_splits:
        matched_a.add(a_index)
        matched_b.update(b_window)
    splits.extend(orphan_splits)

    unmatched_a = [i for i in range(len(a_blocks)) if i not in matched_a]
    unmatched_b = [i for i in range(len(b_blocks)) if i not in matched_b]

    orphan_merges = _detect_groups(unmatched_b, unmatched_a, b_blocks, a_blocks, threshold)
    for b_index, a_window, _score in orphan_merges:
        matched_b.add(b_index)
        matched_a.update(a_window)
    merges.extend(orphan_merges)

    moved = _detect_moves(pairs, options)

    alignments: list[Alignment] = []

    for a_index, b_index, score in pairs:
        distance = None
        if (a_index, b_index) in moved:
            distance = b_index - a_index
        alignments.append(
            Alignment(
                relation=Relation.MATCHED,
                a_indices=(a_index,),
                b_indices=(b_index,),
                similarity=1.0 if (a_index, b_index) in anchor_pairs else score,
                move_distance=distance,
            )
        )

    for a_index, b_window, score in splits:
        alignments.append(
            Alignment(
                relation=Relation.SPLIT,
                a_indices=(a_index,),
                b_indices=b_window,
                similarity=score,
            )
        )

    for b_index, a_window, score in merges:
        alignments.append(
            Alignment(
                relation=Relation.MERGED,
                a_indices=a_window,
                b_indices=(b_index,),
                similarity=score,
            )
        )

    for a_index in sorted(i for i in range(len(a_blocks)) if i not in matched_a):
        alignments.append(Alignment(relation=Relation.DELETED, a_indices=(a_index,), b_indices=()))

    for b_index in sorted(i for i in range(len(b_blocks)) if i not in matched_b):
        alignments.append(Alignment(relation=Relation.INSERTED, a_indices=(), b_indices=(b_index,)))

    return _reading_order(alignments)


def _detect_moves(
    pairs: list[tuple[int, int, float]], options: DiffOptions
) -> set[tuple[int, int]]:
    """Identify aligned pairs whose order is non-monotonic.

    Blocks belonging to the longest increasing subsequence are in their
    original relative order and are not moved; those outside it are the minimal
    set whose displacement explains the reordering.

    Move detection has a real quality ceiling. Repetitive text — verse
    refrains, litanies, epistolary formulae — produces blocks that are
    legitimately near-identical to several candidates, and the alignment may
    pair the wrong ones and report a flurry of moves no author made. Two things
    mitigate it: ``move_threshold`` is deliberately higher than
    ``align_threshold``, so a weak pair is never reported as a move; and the
    reader can switch detection off, because sometimes the right answer is to
    stop a heuristic fighting the text.
    """
    if not options.detect_moves:
        return set()

    ordered = sorted(pairs, key=lambda item: item[0])
    in_place = longest_increasing_subsequence([b for _, b, _ in ordered])

    return {
        (a, b)
        for position, (a, b, score) in enumerate(ordered)
        if position not in in_place and score >= options.move_threshold
    }


def _reading_order(alignments: list[Alignment]) -> list[Alignment]:
    """Order for reading: by B ordinal, with deletions at their A position.

    A deleted block has no B ordinal, so it is placed after the last alignment
    whose A ordinal precedes it. The result cannot be reconstructed from
    ``b_index`` alone, which is why ordering is fixed here rather than left to
    the client.
    """
    with_b = [item for item in alignments if item.b_indices]
    without_b = [item for item in alignments if not item.b_indices]

    with_b.sort(key=lambda item: (min(item.b_indices), min(item.a_indices or (0,))))

    if not without_b:
        return with_b

    result: list[Alignment] = []
    deletions = sorted(without_b, key=lambda item: min(item.a_indices))
    cursor = 0

    for alignment in with_b:
        a_position = min(alignment.a_indices) if alignment.a_indices else -1
        while cursor < len(deletions) and min(deletions[cursor].a_indices) < a_position:
            result.append(deletions[cursor])
            cursor += 1
        result.append(alignment)

    result.extend(deletions[cursor:])
    return result
