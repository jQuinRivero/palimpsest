"""Verse segmentation.

`palimpsest` reads poetry as poetry: a stanza becomes one ``VERSE_LINE`` block
per line, because in verse the line is the unit a scholar compares. A
stanza-sized block reports one changed word as a wholly modified stanza, and
hides a transposed line entirely — moves are detected between blocks, never
inside one.

The heuristic is deliberately biased toward prose, and most of what follows is
about that bias rather than about poems. A missed poem leaves the previous
behaviour; a misjudged paragraph is shattered into blocks that no reader of the
comparison can tell from real structure.

See docs/03-normalization.md.
"""

from __future__ import annotations

import pytest

from app.models import BlockKind, BlockStatus, SourceFormat
from app.services.formatting.payload import build_comparison
from app.services.ingestion.normalize import VERSE_WARNING, normalize

SONNET = (
    "Shall I compare thee to a summer's day?\n"
    "Thou art more lovely and more temperate:\n"
    "Rough winds do shake the darling buds of May,\n"
    "And summer's lease hath all too short a date:"
)


def parse(text: str, *, reflow_lines: bool = False):
    return normalize(
        text,
        document_id="doc_verse",
        title="Verse",
        source_format=SourceFormat.TXT,
        parser_name="test",
        parser_version="1",
        reflow_lines=reflow_lines,
    )


def kinds(document) -> list[BlockKind]:
    return [block.kind for block in document.blocks]


def compare(a_text: str, b_text: str):
    """Collate two witnesses that were segmented by the real pipeline."""
    return build_comparison(
        normalize(
            a_text,
            document_id="doc_a",
            title="A",
            source_format=SourceFormat.TXT,
            parser_name="test",
            parser_version="1",
            witness="a",
        ),
        normalize(
            b_text,
            document_id="doc_b",
            title="B",
            source_format=SourceFormat.TXT,
            parser_name="test",
            parser_version="1",
            witness="b",
        ),
    )


class TestVerseIsSegmented:
    def test_a_quatrain_becomes_one_block_per_line(self) -> None:
        document = parse(SONNET)

        assert kinds(document) == [BlockKind.VERSE_LINE] * 4
        assert [block.text for block in document.blocks] == SONNET.split("\n")

    def test_segmentation_is_announced(self) -> None:
        """Deciding a text is a poem changes the unit of comparison.

        A researcher must be able to see that the tool made that call, because
        if it made it wrongly every downstream count is finer-grained than the
        author's own structure.
        """
        document = parse(SONNET)

        codes = [warning.code for warning in document.warnings]
        assert VERSE_WARNING in codes

        message = next(w.message for w in document.warnings if w.code == VERSE_WARNING)
        assert "4 lines" in message

    def test_stanzas_are_separate_passages(self) -> None:
        two_stanzas = f"{SONNET}\n\n{SONNET}"
        document = parse(two_stanzas)

        assert kinds(document) == [BlockKind.VERSE_LINE] * 8

    def test_verse_survives_a_reflowing_parser(self) -> None:
        """PDF sets ``reflow_lines``; verse must still not be joined."""
        document = parse(SONNET, reflow_lines=True)

        assert kinds(document) == [BlockKind.VERSE_LINE] * 4

    def test_a_changed_word_touches_one_line_only(self) -> None:
        """The point of the whole exercise, stated as an assertion."""
        revised = SONNET.replace("lovely", "comely")
        document = parse(revised)

        assert kinds(document) == [BlockKind.VERSE_LINE] * 4
        original = parse(SONNET)
        differing = [
            index
            for index, (a, b) in enumerate(zip(original.blocks, document.blocks, strict=True))
            if a.text != b.text
        ]
        assert differing == [1]


class TestProseIsNotShredded:
    """False positives are the expensive failure; these are the guard."""

    @pytest.mark.parametrize(
        ("label", "text"),
        [
            (
                "wrapped prose",
                "The argument continues without interruption across the margin and\n"
                "carries on for a further clause before reaching its full stop.",
            ),
            (
                "narrow column prose",
                "The narrow measure of this column means every single line\n"
                "sits close to the same width as all of the other lines\n"
                "which is exactly what typeset prose does on a page\n"
                "and it must not be mistaken for a poem at any point",
            ),
            (
                "a column of initials",
                "A\nB\nC\nD",
            ),
            (
                "a column of figures",
                "1749\n1750\n1751\n1752",
            ),
            (
                "a bare list of single words",
                "Apples\nPears\nPlums\nQuinces",
            ),
            (
                "an address block",
                "Charles Dickens\n48 Doughty Street\nLondon\nEngland",
            ),
            (
                "two lines only",
                "Thou art more lovely and more temperate:\n"
                "Rough winds do shake the darling buds of May,",
            ),
        ],
    )
    def test_is_not_segmented_as_verse(self, label: str, text: str) -> None:
        document = parse(text)

        assert BlockKind.VERSE_LINE not in kinds(document), f"{label} was read as verse"
        assert VERSE_WARNING not in [w.code for w in document.warnings]

    def test_a_long_paragraph_stays_one_block(self) -> None:
        paragraph = (
            "It is a truth universally acknowledged, that a single man in\n"
            "possession of a good fortune, must be in want of a wife.\n"
            "However little known the feelings or views of such a man may be\n"
            "on his first entering a neighbourhood, this truth is so well fixed"
        )
        document = parse(paragraph)

        assert kinds(document) == [BlockKind.PARAGRAPH]


class TestParserSuppliedKindsAreRespected:
    """Only unclassified prose is eligible; a parser that knows, wins."""

    @pytest.mark.parametrize(
        "kind",
        [BlockKind.HEADING, BlockKind.QUOTE, BlockKind.LIST_ITEM, BlockKind.ARTIFACT],
    )
    def test_classified_blocks_are_never_reclassified(self, kind: BlockKind) -> None:
        from app.services.ingestion.normalize import NormalizationBlock

        document = normalize(
            [NormalizationBlock(text=SONNET, kind=kind)],
            document_id="doc_verse",
            title="Verse",
            source_format=SourceFormat.TXT,
            parser_name="test",
            parser_version="1",
        )

        assert kinds(document) == [kind]


class TestVerseAlignment:
    """What line-level blocks actually buy the reader.

    Each of these was impossible before segmentation, because the whole stanza
    was a single block: a one-word revision reported the stanza as modified,
    and a transposed line produced no structural finding at all.
    """

    def test_one_revised_word_marks_one_line(self) -> None:
        result = compare(SONNET, SONNET.replace("lovely", "comely"))

        statuses = [block.status for block in result.blocks]
        assert statuses == [
            BlockStatus.UNCHANGED,
            BlockStatus.MODIFIED,
            BlockStatus.UNCHANGED,
            BlockStatus.UNCHANGED,
        ]

    def test_a_transposed_line_reads_as_a_move_with_no_edits(self) -> None:
        transposed = "\n".join(
            [
                SONNET.split("\n")[0],
                SONNET.split("\n")[2],
                SONNET.split("\n")[1],
                SONNET.split("\n")[3],
            ]
        )
        result = compare(SONNET, transposed)

        assert result.metrics.blocks_moved == 1
        # The poet reordered two lines and changed not one word. Reporting
        # edits here would describe a rewrite that never happened.
        assert result.metrics.edit_count == 0

    def test_a_repeated_refrain_does_not_confuse_alignment(self) -> None:
        """Verse is repetitive, which is the risk line-level blocks introduce.

        An identical refrain in two stanzas offers alignment several equally
        good candidates. It must still pair each refrain with its own stanza's
        and leave both unchanged, rather than manufacturing a move.
        """
        a = (
            "The bell was rung across the empty water\n"
            "And nobody came down to hear it sound\n"
            "Never again, never again, never again\n"
            "\n"
            "The tide went out beyond the harbour wall\n"
            "And nobody came down to watch it go\n"
            "Never again, never again, never again"
        )
        b = a.replace("hear it sound", "hear it ring")

        result = compare(a, b)

        assert [block.status for block in result.blocks] == [
            BlockStatus.UNCHANGED,
            BlockStatus.MODIFIED,
            BlockStatus.UNCHANGED,
            BlockStatus.UNCHANGED,
            BlockStatus.UNCHANGED,
            BlockStatus.UNCHANGED,
        ]
        assert result.metrics.blocks_moved == 0
