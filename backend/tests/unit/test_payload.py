"""End-to-end payload tests.

Every assembled ``ComparisonResult`` must satisfy all eight invariants from
docs/05-data-schema.md. These run the real assertion code, so a contract
violation fails loudly rather than reaching a client.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models import (
    Block,
    BlockKind,
    BlockStatus,
    DiffOptions,
    Document,
    DocumentMetadata,
    SourceFormat,
    TokenStatus,
    assert_comparison,
    block_id,
    check_comparison,
)
from app.services.formatting.payload import build_comparison


def make_document(witness: str, paragraphs: list[str], title: str = "Test") -> Document:
    blocks: list[Block] = []
    cursor = 0
    for index, text in enumerate(paragraphs):
        blocks.append(
            Block(
                id=block_id(witness, index),
                index=index,
                kind=BlockKind.PARAGRAPH,
                text=text,
                char_start=cursor,
                char_end=cursor + len(text),
            )
        )
        cursor += len(text) + 2

    full = "\n\n".join(paragraphs)
    return Document(
        id=f"doc_{witness}_test",
        title=title,
        source_format=SourceFormat.TXT,
        blocks=blocks,
        metadata=DocumentMetadata(
            word_count=sum(len(p.split()) for p in paragraphs),
            block_count=len(blocks),
            char_count=len(full),
            parser_name="TestParser",
            parser_version="1.0.0",
        ),
    )


class TestBuildComparison:
    def test_identical_witnesses(self) -> None:
        doc_a = make_document("a", ["It was a long crossing.", "The waves were grey."])
        doc_b = make_document("b", ["It was a long crossing.", "The waves were grey."])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        assert result.metrics.similarity == 1.0
        assert result.metrics.edit_count == 0
        assert result.metrics.churn == 0.0
        assert all(b.status is BlockStatus.UNCHANGED for b in result.blocks)

    def test_modified_block(self) -> None:
        doc_a = make_document("a", ["The cat sat on the mat."])
        doc_b = make_document("b", ["The black cat sat upon the mat."])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        assert result.blocks[0].status is BlockStatus.MODIFIED
        assert result.metrics.insertions > 0
        assert result.metrics.deletions > 0

    def test_inserted_block(self) -> None:
        doc_a = make_document("a", ["One."])
        doc_b = make_document("b", ["One.", "Two."])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        inserted = [b for b in result.blocks if b.status is BlockStatus.INSERTED]
        assert len(inserted) == 1
        assert inserted[0].a_index is None
        assert inserted[0].b_index == 1

    def test_deleted_block(self) -> None:
        doc_a = make_document("a", ["One.", "Two."])
        doc_b = make_document("b", ["One."])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        deleted = [b for b in result.blocks if b.status is BlockStatus.DELETED]
        assert len(deleted) == 1
        assert deleted[0].b_index is None
        assert deleted[0].a_index == 1

    def test_totally_different_witnesses(self) -> None:
        doc_a = make_document("a", ["Alpha beta gamma delta."])
        doc_b = make_document("b", ["Wholly unrelated prose here."])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        assert result.metrics.similarity < 0.5

    def test_empty_documents(self) -> None:
        doc_a = make_document("a", [])
        doc_b = make_document("b", [])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        assert result.total_blocks == 0
        assert result.metrics.similarity == 1.0

    def test_document_word_counts_reconstruct(self) -> None:
        doc_a = make_document("a", ["one two three", "four five"])
        doc_b = make_document("b", ["one two three", "four five six"])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        assert result.metrics.a_word_count == 5
        assert result.metrics.b_word_count == 6

    def test_reparagraphing_reports_structure_not_rewrite(self) -> None:
        """Phase 1 cannot detect a split, and must not pretend otherwise.

        Documents the honest phase-1 limitation: positional alignment sees a
        modification plus an insertion. Phase 3's alignment layer is what turns
        this into a SPLIT with zero edits.
        """
        doc_a = make_document("a", ["It was a long crossing. The waves were grey."])
        doc_b = make_document("b", ["It was a long crossing.", "The waves were grey."])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        assert result.metrics.blocks_split == 0, "phase 1 has no split detection"

    def test_totals_are_consistent(self) -> None:
        doc_a = make_document("a", ["alpha", "beta", "gamma"])
        doc_b = make_document("b", ["alpha", "BETA", "gamma", "delta"])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        assert result.total_blocks == len(result.blocks)
        assert result.truncated is False

    def test_options_are_echoed(self) -> None:
        options = DiffOptions(ignore_case=True, align_threshold=0.7)
        doc_a = make_document("a", ["Text."])
        doc_b = make_document("b", ["text."])
        result = build_comparison(doc_a, doc_b, options)

        assert_comparison(result)
        assert result.options.ignore_case is True
        assert result.options.align_threshold == 0.7

    def test_unchanged_token_accounting(self) -> None:
        doc_a = make_document("a", ["one two three four"])
        doc_b = make_document("b", ["one two three four"])
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        assert result.metrics.unchanged_tokens == 4
        # Dice over identical witnesses: 2*4/(4+4) == 1.0
        assert result.metrics.similarity == 1.0


class TestInvariantProperties:
    @given(
        st.lists(st.text(min_size=1, max_size=60), min_size=0, max_size=6),
        st.lists(st.text(min_size=1, max_size=60), min_size=0, max_size=6),
    )
    @settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_witnesses_satisfy_invariants(
        self, a_paras: list[str], b_paras: list[str]
    ) -> None:
        result = build_comparison(make_document("a", a_paras), make_document("b", b_paras))
        violations = check_comparison(result)
        assert not violations, "; ".join(violations)

    @given(
        st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=4),
        st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=4),
    )
    @settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_pane_reconstruction_property(self, a_paras: list[str], b_paras: list[str]) -> None:
        """Each pane must reproduce its own witness, block for block."""
        doc_a = make_document("a", a_paras)
        doc_b = make_document("b", b_paras)
        result = build_comparison(doc_a, doc_b)

        for diff_block in result.blocks:
            if diff_block.a_index is not None:
                original = doc_a.blocks[diff_block.a_index].text
                assert "".join(t.text for t in diff_block.a_tokens) == original
            if diff_block.b_index is not None:
                original = doc_b.blocks[diff_block.b_index].text
                assert "".join(t.text for t in diff_block.b_tokens) == original

    @given(st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=4))
    @settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_self_comparison_is_wholly_unchanged(self, paras: list[str]) -> None:
        doc_a = make_document("a", paras)
        doc_b = make_document("b", paras)
        result = build_comparison(doc_a, doc_b)

        assert_comparison(result)
        assert result.metrics.edit_count == 0
        assert all(t.status is TokenStatus.UNCHANGED for b in result.blocks for t in b.tokens)
