"""Dehyphenation and reflow tests.

The hyphenation cases come directly from the worked table in
docs/12-edge-cases.md. The naive rule this module exists to avoid —
``re.sub(r'-\\n(\\w)', r'\\1', text)`` — is asserted against explicitly, because
it is the failure a future contributor is most likely to reintroduce.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.ingestion.dehyphenate import (
    Decision,
    Evidence,
    dehyphenate,
)
from app.services.ingestion.reflow import fold_ligatures, looks_like_verse, reflow


class TestDehyphenationPolicy:
    def test_soft_hyphen_is_closed_up(self) -> None:
        """The common PDF case: a typesetter broke a word to justify a line."""
        text, decisions = dehyphenate("It was an unfor-\ntunate crossing.")
        assert "unfortunate" in text
        assert decisions[0].decision is Decision.JOINED

    def test_naive_rule_would_corrupt_a_real_compound(self) -> None:
        """`self-\\nevident` must not become `selfevident`.

        This is the specific corruption the module exists to prevent.
        """
        source = "A truth held to be self-\nevident by all."
        text, decisions = dehyphenate(source)

        assert "selfevident" not in text
        assert "self-evident" in text
        assert decisions[0].decision is Decision.PRESERVED

    def test_compound_seen_elsewhere_is_the_strongest_signal(self) -> None:
        """A compound written inline elsewhere settles the ambiguous case."""
        source = "The well-being of all.\n\nHe spoke of well-\nbeing often."
        text, decisions = dehyphenate(source)

        assert "wellbeing" not in text
        assert text.count("well-being") == 2
        assert decisions[0].evidence is Evidence.COMPOUND_SEEN_ELSEWHERE

    def test_joined_form_seen_elsewhere_licenses_the_join(self) -> None:
        source = "It was unfortunate.\n\nAn unfor-\ntunate business."
        _, decisions = dehyphenate(source)
        assert decisions[0].decision is Decision.JOINED
        assert decisions[0].evidence is Evidence.JOINED_SEEN_ELSEWHERE

    def test_em_dash_is_punctuation_and_never_closed_up(self) -> None:
        text, decisions = dehyphenate("He saw the visitor\u2014\nstill waiting.")
        assert "visitorstill" not in text
        assert "visitor\u2014still" in text
        # An em dash is not hyphenation at all, so no decision is recorded.
        assert decisions == []

    def test_en_dash_is_punctuation(self) -> None:
        text, _ = dehyphenate("the years 1914\u2013\n1918 were long")
        assert "19141918" not in text

    def test_numeric_ranges_are_preserved(self) -> None:
        _, decisions = dehyphenate("see pages 41-\n52 for detail")
        assert decisions[0].decision is Decision.PRESERVED
        assert decisions[0].evidence is Evidence.NUMERIC

    def test_capitalised_second_fragment_is_preserved(self) -> None:
        _, decisions = dehyphenate("the Anglo-\nSaxon chronicle")
        assert decisions[0].decision is Decision.PRESERVED
        assert decisions[0].evidence is Evidence.CAPITALISED_SECOND

    def test_hyphenated_prefix_is_preserved(self) -> None:
        _, decisions = dehyphenate("he had to re-\nenter the room")
        assert decisions[0].decision is Decision.PRESERVED
        assert decisions[0].evidence is Evidence.HYPHENATED_PREFIX

    def test_multi_part_compound_is_preserved(self) -> None:
        text, _ = dehyphenate("his mother-\nin-law arrived")
        assert "motherin-law" not in text
        assert "mother-in-law" in text

    def test_default_differs_by_provenance(self) -> None:
        """A PDF line break is the typesetter's; a text one is the author's."""
        source = "a zzzq-\nxxvy thing"

        pdf_text, pdf_decisions = dehyphenate(source, join_by_default=True)
        txt_text, txt_decisions = dehyphenate(source, join_by_default=False)

        assert pdf_decisions[0].decision is Decision.JOINED
        assert txt_decisions[0].decision is Decision.PRESERVED
        assert "zzzqxxvy" in pdf_text
        assert "zzzq-xxvy" in txt_text

    @pytest.mark.parametrize(
        ("source", "must_contain", "must_not_contain"),
        [
            ("self-\nevident", "self-evident", "selfevident"),
            ("well-\nbeing", "well-being", "wellbeing"),
            ("re-\nenter", "re-enter", "reenter"),
            ("visitor\u2014\nstill", "visitor\u2014still", "visitorstill"),
            ("mother-\nin-law", "mother-in-law", "motherin"),
        ],
    )
    def test_doc12_worked_table(
        self, source: str, must_contain: str, must_not_contain: str
    ) -> None:
        text, _ = dehyphenate(source)
        assert must_contain in text
        assert must_not_contain not in text

    def test_decisions_are_auditable(self) -> None:
        """Every decision must carry both its outcome and its reason."""
        _, decisions = dehyphenate("self-\nevident and unfor-\ntunate")
        assert len(decisions) == 2
        for decision in decisions:
            assert decision.first and decision.second
            assert decision.decision in (Decision.JOINED, Decision.PRESERVED)
            assert decision.evidence in set(Evidence)

    def test_no_hyphen_is_a_no_op(self) -> None:
        source = "Nothing here is hyphenated across a line."
        text, decisions = dehyphenate(source)
        assert text == source
        assert decisions == []

    @given(st.text(max_size=300))
    @settings(max_examples=200)
    def test_never_raises(self, text: str) -> None:
        result, _ = dehyphenate(text)
        assert isinstance(result, str)

    @given(st.text(max_size=300))
    @settings(max_examples=200)
    def test_idempotent(self, text: str) -> None:
        once, _ = dehyphenate(text)
        twice, _ = dehyphenate(once)
        assert once == twice


class TestLigatures:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("\ufb01nal", "final"),
            ("\ufb02ourish", "flourish"),
            ("di\ufb00erent", "different"),
            ("o\ufb03ce", "office"),
            ("\u0153uvre", "oeuvre"),
        ],
    )
    def test_folds_ligatures(self, source: str, expected: str) -> None:
        assert fold_ligatures(source) == expected

    def test_leaves_curly_quotes_and_dashes_alone(self) -> None:
        """Typography may be authorial, so folding it is a DiffOptions concern."""
        source = "\u2018quoted\u2019 \u201cspeech\u201d \u2014 dash"
        assert fold_ligatures(source) == source


class TestReflow:
    def test_joins_layout_broken_lines(self) -> None:
        source = (
            "It was a long crossing and the waves were grey from\n"
            "the first morning to the last, and he remembered\n"
            "almost nothing of the voyage itself."
        )
        assert "\n" not in reflow(source)
        assert "grey from the first" in reflow(source)

    def test_preserves_verse(self) -> None:
        verse = (
            "Shall I compare thee to a summer's day?\n"
            "Thou art more lovely and more temperate:\n"
            "Rough winds do shake the darling buds of May,\n"
            "And summer's lease hath all too short a date:"
        )
        assert reflow(verse) == verse

    def test_detects_verse(self) -> None:
        verse = [
            "Shall I compare thee to a summer's day?",
            "Thou art more lovely and more temperate:",
            "Rough winds do shake the darling buds of May,",
        ]
        assert looks_like_verse(verse) is True

    def test_prose_is_not_verse(self) -> None:
        prose = [
            "It was a long crossing and the waves were grey from the first",
            "morning to the last, and he remembered almost nothing at all of",
            "the voyage itself, only the cold.",
        ]
        assert looks_like_verse(prose) is False

    def test_single_line_unchanged(self) -> None:
        assert reflow("One line only.") == "One line only."

    def test_empty(self) -> None:
        assert reflow("") == ""

    @given(st.text(max_size=300))
    @settings(max_examples=200)
    def test_idempotent(self, text: str) -> None:
        once = reflow(text)
        assert reflow(once) == once

    @given(st.text(max_size=300))
    @settings(max_examples=150)
    def test_preserves_words(self, text: str) -> None:
        """Reflow may change whitespace but must never lose or invent a word."""
        assert reflow(text).split() == text.split()
