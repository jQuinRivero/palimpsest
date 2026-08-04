"""Normalization with reflow enabled — the PDF ingestion path.

The existing property tests in `test_normalize.py` cover the default path.
These cover `reflow_lines=True`, which engages dehyphenation and line joining
and is therefore where purity is easiest to lose.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.document import BlockKind, SourceFormat
from app.services.ingestion.normalize import (
    DEHYPHENATION_WARNING,
    NormalizationBlock,
    normalize,
)

_TEXT = st.text(max_size=400)


class TestReflowPipeline:
    def test_joins_layout_broken_lines(self) -> None:
        source = (
            "It was a long crossing and the waves were grey from\n"
            "the first morning to the last, and he remembered\n"
            "almost nothing of the voyage itself."
        )
        document = normalize(source, reflow_lines=True)

        assert len(document.blocks) == 1
        assert "\n" not in document.blocks[0].text
        assert "grey from the first" in document.blocks[0].text

    def test_leaves_line_breaks_alone_by_default(self) -> None:
        """Plain text line breaks are the author's own and must survive."""
        source = "First line\nSecond line"
        document = normalize(source)
        assert "\n" in document.blocks[0].text

    def test_dehyphenates_and_warns(self) -> None:
        source = "It was an unfor-\ntunate crossing of the grey water."
        document = normalize(source, reflow_lines=True)

        assert "unfortunate" in document.blocks[0].text
        codes = {warning.code for warning in document.warnings}
        assert DEHYPHENATION_WARNING in codes

    def test_preserved_hyphen_emits_no_warning(self) -> None:
        """A preserved hyphen changes nothing, so there is nothing to report."""
        source = "A truth held to be self-\nevident by all people."
        document = normalize(source, reflow_lines=True)

        assert "self-evident" in document.blocks[0].text
        assert "selfevident" not in document.blocks[0].text
        codes = {warning.code for warning in document.warnings}
        assert DEHYPHENATION_WARNING not in codes

    def test_verse_blocks_are_exempt_from_reflow(self) -> None:
        candidates = [
            NormalizationBlock(
                text=(
                    "Shall I compare thee to a summer's day?\n"
                    "Thou art more lovely and more temperate:\n"
                    "Rough winds do shake the darling buds of May,"
                ),
                kind=BlockKind.VERSE_LINE,
            )
        ]
        document = normalize(candidates, source_format=SourceFormat.PDF, reflow_lines=True)
        assert document.blocks[0].text.count("\n") == 2

    def test_artifact_blocks_are_exempt(self) -> None:
        candidates = [
            NormalizationBlock(text="CHAPTER ONE\n17", kind=BlockKind.ARTIFACT),
        ]
        document = normalize(candidates, source_format=SourceFormat.PDF, reflow_lines=True)
        assert document.blocks[0].kind is BlockKind.ARTIFACT
        assert "\n" in document.blocks[0].text

    def test_ligatures_fold_on_both_paths(self) -> None:
        for reflow_lines in (False, True):
            document = normalize("The \ufb01nal \ufb02ourish", reflow_lines=reflow_lines)
            assert document.blocks[0].text == "The final flourish"

    def test_typography_is_not_folded(self) -> None:
        """Curly quotes may be authorial; folding them is a DiffOptions concern."""
        source = "\u2018quoted\u2019 and \u201cspoken\u201d \u2014 thus"
        document = normalize(source, reflow_lines=True)
        assert "\u2018" in document.blocks[0].text
        assert "\u2014" in document.blocks[0].text

    def test_evidence_crosses_block_boundaries(self) -> None:
        """A compound written inline in one block settles a break in another."""
        candidates = [
            NormalizationBlock(text="The well-being of all was his concern."),
            NormalizationBlock(text="He spoke often of well-\nbeing and of duty."),
        ]
        document = normalize(candidates, source_format=SourceFormat.PDF, reflow_lines=True)
        assert "wellbeing" not in document.blocks[1].text
        assert "well-being" in document.blocks[1].text

    @given(_TEXT)
    @settings(max_examples=200)
    def test_idempotent_with_reflow(self, text: str) -> None:
        once = normalize(text, reflow_lines=True)
        twice = normalize(once, reflow_lines=True)
        assert [b.text for b in once.blocks] == [b.text for b in twice.blocks]

    @given(_TEXT)
    @settings(max_examples=200)
    def test_deterministic_with_reflow(self, text: str) -> None:
        first = normalize(text, reflow_lines=True)
        second = normalize(text, reflow_lines=True)
        assert first.model_dump() == second.model_dump()

    @given(_TEXT)
    @settings(max_examples=200)
    def test_offsets_slice_back_with_reflow(self, text: str) -> None:
        document = normalize(text, reflow_lines=True)
        full = document.full_text()
        for block in document.blocks:
            assert full[block.char_start : block.char_end] == block.text
