"""Alignment tests.

Alignment is what distinguishes this tool from a line diff, so these check the
distinctions it is supposed to draw — and, just as importantly, the ones it is
supposed to refuse to draw.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.diff import DiffOptions
from app.models.document import Block, BlockKind
from app.services.diffing.alignment import (
    Relation,
    align,
    longest_increasing_subsequence,
    similarity,
)


def blocks(texts: list[str], witness: str = "a") -> list[Block]:
    return [
        Block(
            id=f"blk_{witness}_{index:04d}",
            index=index,
            kind=BlockKind.PARAGRAPH,
            text=text,
            char_start=0,
            char_end=len(text),
        )
        for index, text in enumerate(texts)
    ]


def relations(alignments: list[object]) -> list[Relation]:
    return [a.relation for a in alignments]  # type: ignore[attr-defined]


class TestLongestIncreasingSubsequence:
    def test_already_sorted(self) -> None:
        assert longest_increasing_subsequence([0, 1, 2, 3]) == {0, 1, 2, 3}

    def test_identifies_the_minimal_displaced_set(self) -> None:
        """One paragraph lifted out of a chapter must not flag the chapter.

        [2, 0, 1] means the third block moved to the front. The minimal
        explanation is that one block moved, not that two did.
        """
        in_place = longest_increasing_subsequence([2, 0, 1])
        assert len(in_place) == 2
        assert 0 not in in_place

    def test_empty(self) -> None:
        assert longest_increasing_subsequence([]) == set()

    def test_fully_reversed(self) -> None:
        assert len(longest_increasing_subsequence([3, 2, 1, 0])) == 1


class TestSimilarity:
    def test_identical(self) -> None:
        assert similarity("the same text", "the same text") == 1.0

    def test_unrelated(self) -> None:
        assert similarity("alpha beta gamma", "wholly different words") < 0.5

    def test_order_sensitive(self) -> None:
        """A scrambled paragraph is not a match for its original."""
        original = "the cat sat upon the ancient woven mat"
        scrambled = "mat woven ancient the upon sat cat the"
        assert similarity(original, scrambled) < 0.9

    def test_both_empty(self) -> None:
        assert similarity("", "") == 1.0

    def test_one_empty(self) -> None:
        assert similarity("something", "") == 0.0


class TestAlignment:
    def test_identical_witnesses_all_match(self) -> None:
        texts = ["Alpha here.", "Beta here.", "Gamma here."]
        result = align(blocks(texts), blocks(texts, "b"))
        assert relations(result) == [Relation.MATCHED] * 3

    def test_pure_insertion(self) -> None:
        result = align(blocks(["Alpha here."]), blocks(["Alpha here.", "Newly added."], "b"))
        assert Relation.INSERTED in relations(result)

    def test_pure_deletion(self) -> None:
        result = align(blocks(["Alpha here.", "Removed entirely."]), blocks(["Alpha here."], "b"))
        assert Relation.DELETED in relations(result)

    def test_move_is_detected(self) -> None:
        result = align(
            blocks(["Alpha here.", "Beta here.", "Gamma here."]),
            blocks(["Gamma here.", "Alpha here.", "Beta here."], "b"),
        )
        moved = [a for a in result if a.move_distance is not None]
        assert len(moved) == 1
        assert moved[0].a_index == 2 and moved[0].b_index == 0

    def test_split_is_detected(self) -> None:
        result = align(
            blocks(["It was a long crossing. The waves were grey from first to last."]),
            blocks(
                ["It was a long crossing.", "The waves were grey from first to last."],
                "b",
            ),
        )
        splits = [a for a in result if a.relation is Relation.SPLIT]
        assert len(splits) == 1
        assert len(splits[0].b_indices) == 2

    def test_merge_is_detected(self) -> None:
        result = align(
            blocks(["It was a long crossing.", "The waves were grey from first to last."]),
            blocks(["It was a long crossing. The waves were grey from first to last."], "b"),
        )
        merges = [a for a in result if a.relation is Relation.MERGED]
        assert len(merges) == 1
        assert len(merges[0].a_indices) == 2

    def test_unrelated_texts_are_not_paired(self) -> None:
        """Below threshold, alignment must decline rather than guess."""
        result = align(
            blocks(["Alpha beta gamma delta epsilon."]),
            blocks(["Wholly unrelated prose appears here now."], "b"),
        )
        assert set(relations(result)) == {Relation.DELETED, Relation.INSERTED}

    def test_no_spurious_split_when_one_member_already_matches(self) -> None:
        """The SPLIT_MARGIN guard: a good pair must not absorb a neighbour."""
        result = align(
            blocks(["It was a long crossing over grey water."]),
            blocks(
                [
                    "It was a long crossing over grey water.",
                    "An entirely separate observation about birds.",
                ],
                "b",
            ),
        )
        assert Relation.SPLIT not in relations(result)
        assert Relation.INSERTED in relations(result)

    def test_move_detection_respects_the_option(self) -> None:
        result = align(
            blocks(["Alpha here.", "Beta here.", "Gamma here."]),
            blocks(["Gamma here.", "Alpha here.", "Beta here."], "b"),
            DiffOptions(detect_moves=False),
        )
        assert all(a.move_distance is None for a in result)

    def test_weak_pairs_are_never_reported_as_moves(self) -> None:
        """move_threshold is higher than align_threshold on purpose."""
        options = DiffOptions(align_threshold=0.3, move_threshold=0.95)
        result = align(
            blocks(["Alpha one two three.", "Beta four five six."]),
            blocks(["Beta four five seven.", "Alpha one two eight."], "b"),
            options,
        )
        assert all(a.move_distance is None for a in result)

    def test_empty_witnesses(self) -> None:
        assert align([], []) == []

    def test_everything_deleted(self) -> None:
        result = align(blocks(["Alpha.", "Beta."]), [])
        assert relations(result) == [Relation.DELETED, Relation.DELETED]

    def test_everything_inserted(self) -> None:
        result = align([], blocks(["Alpha.", "Beta."], "b"))
        assert relations(result) == [Relation.INSERTED, Relation.INSERTED]

    def test_repeated_text_is_left_to_scoring(self) -> None:
        """Duplicate blocks are ambiguous and must not be anchored blindly."""
        result = align(
            blocks(["Refrain.", "Verse one.", "Refrain."]),
            blocks(["Refrain.", "Verse one.", "Refrain."], "b"),
        )
        # However they pair, every block must be accounted for exactly once.
        a_seen = [i for a in result for i in a.a_indices]
        b_seen = [i for a in result for i in a.b_indices]
        assert sorted(a_seen) == [0, 1, 2]
        assert sorted(b_seen) == [0, 1, 2]

    @given(
        st.lists(st.text(min_size=1, max_size=40), min_size=0, max_size=6),
        st.lists(st.text(min_size=1, max_size=40), min_size=0, max_size=6),
    )
    @settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_every_block_is_accounted_for_exactly_once(
        self, a_texts: list[str], b_texts: list[str]
    ) -> None:
        """Alignment may not lose or duplicate a block, whatever it decides."""
        result = align(blocks(a_texts), blocks(b_texts, "b"))

        a_seen = [i for a in result for i in a.a_indices]
        b_seen = [i for a in result for i in a.b_indices]

        assert sorted(a_seen) == list(range(len(a_texts)))
        assert sorted(b_seen) == list(range(len(b_texts)))

    @given(
        st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=5),
        st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=5),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_alignment_is_deterministic(self, a_texts: list[str], b_texts: list[str]) -> None:
        """Required by the golden corpus: same input, byte-identical output."""
        first = align(blocks(a_texts), blocks(b_texts, "b"))
        second = align(blocks(a_texts), blocks(b_texts, "b"))
        assert first == second
