from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.document import BlockKind, SourceFormat
from app.services.ingestion.normalize import NormalizationBlock, normalize


@pytest.mark.parametrize(
    ("source", "expected_blocks"),
    [
        ("Cafe\u0301", ["Café"]),
        ("A\r\nB\rC", ["A\nB\nC"]),
        (" A  spaced\tline  ", ["A spaced line"]),
        ("First\n\n\nSecond", ["First", "Second"]),
        ("Line one  \nLine\ttwo", ["Line one\nLine two"]),
    ],
)
def test_normalization_table(source: str, expected_blocks: list[str]) -> None:
    document = normalize(
        source,
        document_id="doc_case",
        title="Case",
        source_format=SourceFormat.TXT,
        parser_name="test",
        parser_version="1",
    )

    assert [block.text for block in document.blocks] == expected_blocks


def test_segmentation_assigns_offsets_into_full_text() -> None:
    document = normalize("First\n\nSecond\n\nThird", document_id="doc_offsets")

    assert document.full_text() == "First\n\nSecond\n\nThird"
    for block in document.blocks:
        assert block.char_end - block.char_start == len(block.text)
        assert document.full_text()[block.char_start : block.char_end] == block.text


def test_normalization_preserves_parser_supplied_kind() -> None:
    document = normalize(
        [
            NormalizationBlock(text="  Chapter 1  ", kind=BlockKind.HEADING, style="Heading 1"),
            NormalizationBlock(text="Body", kind=BlockKind.PARAGRAPH),
        ],
        document_id="doc_kinds",
    )

    assert [block.kind for block in document.blocks] == [BlockKind.HEADING, BlockKind.PARAGRAPH]
    assert document.blocks[0].style == "Heading 1"


def test_metadata_counts_reconstructed_full_text() -> None:
    document = normalize("One two\n\nThree", document_id="doc_counts")

    assert document.metadata.word_count == 3
    assert document.metadata.block_count == 2
    assert document.metadata.char_count == len(document.full_text())


_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=200)


@given(_TEXT)
@settings(max_examples=75)
def test_normalize_is_idempotent(text: str) -> None:
    once = normalize(text, document_id="doc_property")
    twice = normalize(once)

    assert twice == once


@given(_TEXT)
@settings(max_examples=75)
def test_normalize_is_deterministic(text: str) -> None:
    first = normalize(text, document_id="doc_property")
    second = normalize(text, document_id="doc_property")

    assert second == first


@given(_TEXT)
@settings(max_examples=75)
def test_offsets_always_slice_back_to_block_text(text: str) -> None:
    document = normalize(text, document_id="doc_offsets_property")
    full_text = document.full_text()

    for block in document.blocks:
        assert full_text[block.char_start : block.char_end] == block.text
