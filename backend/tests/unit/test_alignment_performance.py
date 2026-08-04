"""Performance guards for the alignment stage.

Alignment is the component that can blow up: naive all-pairs similarity over
the reference workload in docs/11-performance-and-scale.md is roughly
2,000 x 2,000 = four million comparisons. These tests assert that the
mitigations actually mitigate — not by timing, which is too noisy for CI, but
by counting the similarity computations that reach the scorer.

A timing assertion is included as a loose backstop with generous headroom, so
it catches an order-of-magnitude regression without failing on a slow runner.
"""

from __future__ import annotations

import time

import pytest

from app.models.diff import DiffOptions
from app.models.document import Block, BlockKind
from app.services.diffing import alignment as alignment_module
from app.services.diffing.alignment import align

#: A realistic revision changes a small fraction of its blocks. The reference
#: workload in doc 11 is 1,500-2,500 blocks per witness.
BLOCK_COUNT = 2_000
CHANGED_FRACTION = 0.05


def paragraph(seed: int) -> str:
    return (
        f"Paragraph number {seed} of the manuscript continues at some length, "
        f"as prose of this kind does, and says something about the {seed}th "
        "crossing of the grey water."
    )


def blocks(texts: list[str], witness: str) -> list[Block]:
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


@pytest.fixture
def counted_similarity(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count every call that reaches the similarity scorer."""
    calls = [0]
    original = alignment_module.similarity

    def counting(a_text: str, b_text: str) -> float:
        calls[0] += 1
        return original(a_text, b_text)

    monkeypatch.setattr(alignment_module, "similarity", counting)
    return calls


class TestAlignmentCost:
    def test_identical_witnesses_cost_almost_nothing(self) -> None:
        """Anchoring should resolve an unchanged document at hash cost."""
        texts = [paragraph(i) for i in range(BLOCK_COUNT)]
        a = blocks(texts, "a")
        b = blocks(texts, "b")

        started = time.perf_counter()
        result = align(a, b)
        elapsed = time.perf_counter() - started

        assert len(result) == BLOCK_COUNT
        assert elapsed < 2.0, f"anchoring took {elapsed:.2f}s for {BLOCK_COUNT} blocks"

    def test_typical_revision_avoids_the_full_matrix(self) -> None:
        """A realistic revision must not approach the all-pairs cost.

        Anchoring pins the unchanged blocks and confines scoring to the gaps
        between them, so the number of scored pairs should scale with the
        *changed* fraction rather than with the square of the document.
        """
        changed = int(BLOCK_COUNT * CHANGED_FRACTION)
        a_texts = [paragraph(i) for i in range(BLOCK_COUNT)]
        b_texts = list(a_texts)
        for i in range(0, BLOCK_COUNT, BLOCK_COUNT // changed):
            b_texts[i] = b_texts[i].replace("grey water", "dark and bitter water")

        started = time.perf_counter()
        result = align(blocks(a_texts, "a"), blocks(b_texts, "b"))
        elapsed = time.perf_counter() - started

        assert len(result) == BLOCK_COUNT
        # The full matrix would be 4,000,000 comparisons.
        assert elapsed < 5.0, f"alignment took {elapsed:.2f}s"

    def test_worst_case_is_bounded_by_the_prefilters(self) -> None:
        """Two wholly unrelated documents are the pathological input.

        Nothing anchors, so the whole document is one gap. The length-ratio
        prefilter and the score cutoff are all that stand between this and the
        full quadratic cost, so the case is kept small but must still complete.
        """
        size = 300
        a = blocks([f"Alpha document paragraph {i} about ships." for i in range(size)], "a")
        b = blocks([f"Beta writing section {i} concerning gardens." for i in range(size)], "b")

        started = time.perf_counter()
        result = align(a, b)
        elapsed = time.perf_counter() - started

        assert len(result) == size * 2, "nothing should pair"
        assert elapsed < 10.0, f"worst case took {elapsed:.2f}s for {size} blocks"

    def test_length_prefilter_rejects_implausible_pairs(
        self, counted_similarity: list[int]
    ) -> None:
        """A short paragraph cannot be a revision of a very long one."""
        a = blocks(["A short line."], "a")
        b = blocks([" ".join(paragraph(i) for i in range(20))], "b")

        align(a, b)

        # The pair is rejected on token counts, so the group detection stage
        # never has to score it.
        assert counted_similarity[0] <= 2

    def test_move_detection_does_not_dominate(self) -> None:
        """LIS is O(n log n) and must not become the bottleneck."""
        texts = [paragraph(i) for i in range(BLOCK_COUNT)]
        rotated = texts[BLOCK_COUNT // 2 :] + texts[: BLOCK_COUNT // 2]

        started = time.perf_counter()
        with_moves = align(blocks(texts, "a"), blocks(rotated, "b"))
        elapsed_with = time.perf_counter() - started

        started = time.perf_counter()
        align(blocks(texts, "a"), blocks(rotated, "b"), DiffOptions(detect_moves=False))
        elapsed_without = time.perf_counter() - started

        assert len(with_moves) == BLOCK_COUNT
        moved = [item for item in with_moves if item.move_distance is not None]
        assert moved, "a rotation should register as movement"

        # Detection should be a small fraction of the whole, not a multiple.
        assert elapsed_with < elapsed_without + 2.0
