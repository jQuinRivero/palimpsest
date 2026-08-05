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

from app.models import BlockKind, BlockStatus, SourceFormat, StanzaBoundary
from app.services.formatting.payload import build_comparison
from app.services.ingestion.base import DocumentSource
from app.services.ingestion.markdown import MarkdownParser
from app.services.ingestion.normalize import VERSE_WARNING, normalize
from app.services.ingestion.plaintext import PlainTextParser

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


class TestStanzaBoundaries:
    """A stanza break is a formal revision that changes no words.

    Before these, dividing an octave into two quatrains produced similarity
    1.000 and no finding of any kind — the tool asserting that two formally
    different poems were the same. See ADR-0007.
    """

    OCTAVE = "\n".join(
        [
            "Shall I compare thee to a summer's day?",
            "Thou art more lovely and more temperate:",
            "Rough winds do shake the darling buds of May,",
            "And summer's lease hath all too short a date:",
            "Sometime too hot the eye of heaven shines,",
            "And often is his gold complexion dimm'd;",
        ]
    )

    @property
    def two_stanzas(self) -> str:
        lines = self.OCTAVE.split("\n")
        return "\n".join(lines[:3]) + "\n\n" + "\n".join(lines[3:])

    def test_only_the_first_line_of_a_stanza_starts_one(self) -> None:
        document = parse(self.two_stanzas)

        assert [block.starts_stanza for block in document.blocks] == [
            True,
            False,
            False,
            True,
            False,
            False,
        ]

    def test_prose_never_starts_a_stanza(self) -> None:
        document = parse("An ordinary paragraph.\n\nAnd a second one.")

        assert all(not block.starts_stanza for block in document.blocks)

    def test_an_added_break_is_reported_without_any_edit(self) -> None:
        result = compare(self.OCTAVE, self.two_stanzas)

        assert result.metrics.edit_count == 0
        assert result.metrics.stanza_breaks_changed == 1

        boundaries = [block.stanza_boundary for block in result.blocks]
        assert boundaries[0] is StanzaBoundary.SHARED
        assert boundaries[3] is StanzaBoundary.B_ONLY
        assert boundaries.count(StanzaBoundary.B_ONLY) == 1

    def test_a_removed_break_is_reported_from_the_other_side(self) -> None:
        result = compare(self.two_stanzas, self.OCTAVE)

        assert result.metrics.stanza_breaks_changed == 1
        assert result.blocks[3].stanza_boundary is StanzaBoundary.A_ONLY

    def test_matching_stanzas_report_no_change(self) -> None:
        result = compare(self.two_stanzas, self.two_stanzas)

        assert result.metrics.stanza_breaks_changed == 0
        assert result.blocks[0].stanza_boundary is StanzaBoundary.SHARED
        assert result.blocks[1].stanza_boundary is StanzaBoundary.NONE

    def test_prose_carries_no_boundary_at_all(self) -> None:
        """Non-null exactly where it means something, like move_distance."""
        result = compare("A plain paragraph here.", "A plain paragraph there.")

        assert all(block.stanza_boundary is None for block in result.blocks)

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


class TestFormatDoesNotChangeTheFinding:
    """The same poem must collate the same however it was typed.

    Markdown used to join a paragraph's lines with a space, on the reasoning
    that CommonMark renders a soft break as a space. This is not a renderer:
    the line breaks an author typed are evidence about the text, and joining
    them made the same sonnet read as four verse lines from a .txt file and a
    single paragraph from a .md file — which then collated as four MERGED
    blocks, a structural revision nobody made.
    """

    def markdown(self, text: str):
        raw = text.encode("utf-8")
        return MarkdownParser().parse(
            DocumentSource(
                filename="poem.md",
                media_type="text/markdown",
                size_bytes=len(raw),
                data=raw,
            )
        )

    def plaintext(self, text: str):
        raw = text.encode("utf-8")
        return PlainTextParser().parse(
            DocumentSource(
                filename="poem.txt",
                media_type="text/plain",
                size_bytes=len(raw),
                data=raw,
            )
        )

    def test_markdown_reads_verse_as_verse(self) -> None:
        document = self.markdown(SONNET)

        assert [block.kind for block in document.blocks] == [BlockKind.VERSE_LINE] * 4

    def test_the_same_poem_in_two_formats_collates_as_unchanged(self) -> None:
        result = build_comparison(self.plaintext(SONNET), self.markdown(SONNET))

        assert [block.status for block in result.blocks] == [BlockStatus.UNCHANGED] * 4
        assert result.metrics.edit_count == 0
        # The finding that used to appear here, and should not: a file format
        # is not a revision.
        assert result.metrics.blocks_merged == 0
        assert result.metrics.blocks_split == 0

    def test_wrapped_markdown_prose_is_still_one_block(self) -> None:
        """Preserving line breaks must not shred hard-wrapped prose."""
        wrapped = (
            "It is a truth universally acknowledged, that a single man in\n"
            "possession of a good fortune, must be in want of a wife. However\n"
            "little known the feelings or views of such a man may be on his\n"
            "first entering a neighbourhood, this truth is so well fixed."
        )
        document = self.markdown(wrapped)

        assert [block.kind for block in document.blocks] == [BlockKind.PARAGRAPH]

    def test_wrapped_prose_compares_equal_across_formats(self) -> None:
        """Line breaks are kept, so they must not become differences."""
        wrapped = (
            "It is a truth universally acknowledged, that a single man in\n"
            "possession of a good fortune, must be in want of a wife. However\n"
            "little known the feelings or views of such a man may be."
        )
        unwrapped = " ".join(line.strip() for line in wrapped.split("\n"))

        result = build_comparison(self.markdown(wrapped), self.plaintext(unwrapped))

        assert result.metrics.edit_count == 0

    def test_inline_formatting_is_still_stripped(self) -> None:
        document = self.markdown("A **bold** claim here.\nAnd an *emphatic* one.")

        text = " ".join(block.text for block in document.blocks)
        assert "**" not in text
        assert "*" not in text
        assert "bold" in text
        assert "emphatic" in text
