"""Characters that cannot be represented in XML.

The TEI export is built with ElementTree, which escapes markup but does not
validate character ranges: XML 1.0 admits only tab, newline and carriage return
below U+0020, and there is no escape for the others — not even a numeric
reference. So a NUL or an ESC in a witness used to serialise intact and the
researcher received an archive no parser would open, with nothing having
failed anywhere along the way.

These are pinned here rather than only in the TEI tests because the guarantee
belongs to the canonical document: every consumer of normalized text gets to
assume it is representable.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from app.models import DiffOptions
from app.models.document import SourceFormat
from app.services.formatting.payload import build_comparison
from app.services.formatting.tei import build_tei
from app.services.ingestion.normalize import CONTROL_CHARACTER_WARNING, normalize


def norm(text: str, *, title: str = "Case", document_id: str = "doc_ctrl"):
    return normalize(
        text,
        document_id=document_id,
        title=title,
        source_format=SourceFormat.TXT,
        parser_name="test",
        parser_version="1",
    )


@pytest.mark.parametrize(
    ("label", "raw"),
    [
        ("nul", "It was the best\x00 of times."),
        ("vertical tab", "It was the\x0b best of times."),
        ("escape", "It was the \x1b[31mbest\x1b[0m of times."),
        ("backspace", "It was the bes\x08t of times."),
        ("delete", "It was the best\x7f of times."),
    ],
)
def test_forbidden_controls_do_not_reach_canonical_text(label: str, raw: str) -> None:
    document = norm(raw)
    text = document.full_text()

    assert not [character for character in text if ord(character) < 0x20 and character != "\n"]
    assert "\x7f" not in text
    assert "best" in text or "bes" in text


def test_form_feed_becomes_a_break_rather_than_a_deletion() -> None:
    # A form feed in a plain-text witness is a page break someone meant. It
    # cannot survive as itself, but it is a break, not noise.
    document = norm("Chapter One.\n\n\x0cChapter Two.")

    assert [block.text for block in document.blocks] == ["Chapter One.", "Chapter Two."]
    assert "\x0c" not in document.full_text()


def test_form_feed_alone_is_not_announced() -> None:
    # Nothing was lost, so nothing is claimed. Line-ending normalization is
    # silent for the same reason.
    document = norm("Chapter One.\n\n\x0cChapter Two.")

    assert CONTROL_CHARACTER_WARNING not in [warning.code for warning in document.warnings]


def test_removal_is_announced() -> None:
    document = norm("It was the best\x00 of times.")

    codes = [warning.code for warning in document.warnings]
    assert CONTROL_CHARACTER_WARNING in codes


def test_title_is_reduced_to_one_clean_line() -> None:
    # Titles come from the upload filename: the one field the researcher never
    # typed and an attacker fully controls. It reaches the TEI header without
    # passing through block normalization.
    document = norm("It was the best of times.", title="Witness\x00A\nsecond  line")

    assert document.title == "WitnessA second line"
    assert CONTROL_CHARACTER_WARNING in [warning.code for warning in document.warnings]


@pytest.mark.parametrize(
    "raw",
    [
        "It was the best\x00 of times.",
        "It was the\x0b best of times.",
        "It was the \x1b[31mbest\x1b[0m of times.",
        "Chapter One.\n\n\x0cChapter Two.",
        # Markup metacharacters were always safe — ElementTree escapes them —
        # and stay here so a change of serialiser cannot quietly break it.
        "a < b & c > d ]]> e",
    ],
)
def test_tei_export_parses_for_a_witness_that_contained_controls(raw: str) -> None:
    a = norm(raw, document_id="doc_a", title="A")
    b = norm(raw.replace("best", "worst").replace("One", "Two"), document_id="doc_b", title="B")

    tei = build_tei(build_comparison(a, b, DiffOptions()))

    # The assertion is that this does not raise. An export that cannot be
    # parsed is not an archive.
    ET.fromstring(tei)
