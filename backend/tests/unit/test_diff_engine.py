"""Tokenizer and word-level diff engine tests.

The reconstruction property — concatenating a token stream reproduces the
source text exactly — is the cheapest high-value check in the system: if it
holds, the diff neither invented nor lost a character.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.diff import DiffOptions, Granularity, TokenStatus
from app.services.diffing.engine import diff_tokens
from app.services.diffing.tokenizer import comparison_key, tokenize


def _text(tokens: list[object]) -> str:
    return "".join(t.text for t in tokens)  # type: ignore[attr-defined]


class TestTokenize:
    def test_carries_trailing_whitespace(self) -> None:
        assert tokenize("The cat sat") == ["The ", "cat ", "sat"]

    def test_reconstruction(self) -> None:
        text = "The cat  sat\non the mat.\n\nA new paragraph."
        assert "".join(tokenize(text)) == text

    def test_leading_whitespace_preserved(self) -> None:
        text = "   indented start"
        assert "".join(tokenize(text)) == text

    def test_empty(self) -> None:
        assert tokenize("") == []

    def test_whitespace_only(self) -> None:
        assert "".join(tokenize("   \n  ")) == "   \n  "

    def test_character_granularity(self) -> None:
        assert tokenize("ab c", Granularity.CHARACTER) == ["a", "b", " ", "c"]

    @given(st.text())
    @settings(max_examples=300)
    def test_reconstruction_property(self, text: str) -> None:
        assert "".join(tokenize(text)) == text

    @given(st.text())
    @settings(max_examples=200)
    def test_character_reconstruction_property(self, text: str) -> None:
        assert "".join(tokenize(text, Granularity.CHARACTER)) == text


class TestComparisonKey:
    def test_ignore_case(self) -> None:
        options = DiffOptions(ignore_case=True)
        assert comparison_key("The ", options) == comparison_key("the ", options)

    def test_case_significant_by_default(self) -> None:
        options = DiffOptions()
        assert comparison_key("The ", options) != comparison_key("the ", options)

    def test_ignore_punctuation(self) -> None:
        options = DiffOptions(ignore_punctuation=True)
        assert comparison_key("mat.", options) == comparison_key("mat", options)

    def test_punctuation_significant_by_default(self) -> None:
        assert comparison_key("mat.", DiffOptions()) != comparison_key("mat", DiffOptions())


class TestDiffTokens:
    def test_spec_worked_example(self) -> None:
        """The worked example in docs/04-diff-engine.md must actually hold."""
        a = "The cat sat on the mat."
        b = "The black cat sat upon the mat."
        tokens, a_tokens, b_tokens = diff_tokens(a, b)

        assert _text(a_tokens) == a
        assert _text(b_tokens) == b

        inserted = [t.text for t in tokens if t.status is TokenStatus.INSERTION]
        deleted = [t.text for t in tokens if t.status is TokenStatus.DELETION]

        assert "black " in "".join(inserted)
        assert "upon " in "".join(inserted)
        assert "on " in "".join(deleted)

        # Word-level, not character-level: `on` -> `upon` must not be reported
        # as an insertion of the two characters `up`.
        assert not any(t.text.strip() == "up" for t in tokens)

    def test_identical_texts_are_all_unchanged(self) -> None:
        text = "It was a long crossing."
        tokens, a_tokens, b_tokens = diff_tokens(text, text)
        assert all(t.status is TokenStatus.UNCHANGED for t in tokens)
        assert _text(a_tokens) == text
        assert _text(b_tokens) == text

    def test_pure_insertion(self) -> None:
        tokens, a_tokens, b_tokens = diff_tokens("", "brand new text")
        assert _text(a_tokens) == ""
        assert _text(b_tokens) == "brand new text"
        assert all(t.status is TokenStatus.INSERTION for t in tokens)

    def test_pure_deletion(self) -> None:
        tokens, a_tokens, b_tokens = diff_tokens("gone entirely", "")
        assert _text(a_tokens) == "gone entirely"
        assert _text(b_tokens) == ""
        assert all(t.status is TokenStatus.DELETION for t in tokens)

    def test_both_empty(self) -> None:
        tokens, a_tokens, b_tokens = diff_tokens("", "")
        assert tokens == [] and a_tokens == [] and b_tokens == []

    def test_streams_are_pure(self) -> None:
        _, a_tokens, b_tokens = diff_tokens("the quick brown fox", "the slow brown dog")
        assert all(t.status is not TokenStatus.INSERTION for t in a_tokens)
        assert all(t.status is not TokenStatus.DELETION for t in b_tokens)

    def test_unified_stream_reproduces_both_panes(self) -> None:
        """The unified stream matches each pane word for word.

        It is not required to match whitespace: it interleaves runs that were
        never adjacent in either witness and must keep them separated so words
        cannot fuse. Each pane separately reproduces its own witness exactly,
        which is what this test asserts first.
        """
        a = "one two three four five"
        b = "one two THREE four six"
        tokens, a_tokens, b_tokens = diff_tokens(a, b)

        assert _text(a_tokens) == a
        assert _text(b_tokens) == b

        from_unified_a = "".join(t.text for t in tokens if t.status is not TokenStatus.INSERTION)
        from_unified_b = "".join(t.text for t in tokens if t.status is not TokenStatus.DELETION)
        assert from_unified_a.split() == a.split()
        assert from_unified_b.split() == b.split()

    def test_tokens_are_coalesced_runs(self) -> None:
        """Adjacent same-status words must merge into one Token object."""
        tokens, _, _ = diff_tokens("alpha beta gamma", "alpha beta gamma")
        assert len(tokens) == 1
        assert tokens[0].text == "alpha beta gamma"
        assert tokens[0].word_count() == 3

    def test_ignore_case_folds_comparison_but_keeps_surface(self) -> None:
        tokens, a_tokens, b_tokens = diff_tokens(
            "The Cat Sat", "the cat sat", DiffOptions(ignore_case=True)
        )
        assert all(t.status is TokenStatus.UNCHANGED for t in tokens)
        # Surface forms are preserved per witness even though they compared equal.
        assert _text(a_tokens) == "The Cat Sat"
        assert _text(b_tokens) == "the cat sat"

    def test_reordering_is_not_silently_equal(self) -> None:
        tokens, _, _ = diff_tokens("alpha beta", "beta alpha")
        assert any(t.status is not TokenStatus.UNCHANGED for t in tokens)

    def test_unified_stream_never_fuses_words(self) -> None:
        """Regression: an equal run whose trailing whitespace differs between
        witnesses must not glue the following insertion onto the last word.

        A ends the block at "five"; B continues "five six". Under
        normalize_whitespace those runs compare equal, and naively taking A's
        surface produced "four fivesix" in the unified stream.
        """
        tokens, a_tokens, b_tokens = diff_tokens("four five", "four five six")

        assert _text(a_tokens) == "four five"
        assert _text(b_tokens) == "four five six"

        unified = _text(tokens)
        assert "fivesix" not in unified
        assert unified.split() == ["four", "five", "six"]

    def test_unified_stream_never_fuses_words_reversed(self) -> None:
        """The mirror case: the deletion side."""
        tokens, a_tokens, b_tokens = diff_tokens("four five six", "four five")

        assert _text(a_tokens) == "four five six"
        assert _text(b_tokens) == "four five"
        assert "fivesix" not in _text(tokens)

    @given(
        st.lists(st.sampled_from(["alpha", "beta", "gamma", "delta"]), min_size=1, max_size=8),
        st.lists(st.sampled_from(["alpha", "beta", "gamma", "delta"]), min_size=1, max_size=8),
    )
    @settings(max_examples=300, deadline=None)
    def test_unified_words_are_never_fused_property(
        self, a_words: list[str], b_words: list[str]
    ) -> None:
        """No word in the unified stream may be a concatenation of two others.

        Regression guard for two distinct fusion bugs: an equal run whose
        trailing whitespace differed between witnesses ("four five" + "six"
        -> "four fivesix"), and a deletion followed directly by an insertion
        ("alpha" + "beta" -> "alphabeta").
        """
        a = " ".join(a_words)
        b = " ".join(b_words)
        tokens, _, _ = diff_tokens(a, b)

        vocabulary = {"alpha", "beta", "gamma", "delta"}
        for word in _text(tokens).split():
            assert word in vocabulary, f"{word!r} is a fusion in {_text(tokens)!r}"

    @given(
        st.lists(st.sampled_from(["alpha", "beta", "gamma", "delta"]), min_size=1, max_size=6),
        st.lists(st.sampled_from(["alpha", "beta", "gamma", "delta"]), min_size=1, max_size=6),
    )
    @settings(max_examples=200, deadline=None)
    def test_unified_projections_match_panes_word_for_word(
        self, a_words: list[str], b_words: list[str]
    ) -> None:
        """Filtering the unified stream must recover each witness's words."""
        a = " ".join(a_words)
        b = " ".join(b_words)
        tokens, a_tokens, b_tokens = diff_tokens(a, b)

        from_a = "".join(t.text for t in tokens if t.status is not TokenStatus.INSERTION)
        from_b = "".join(t.text for t in tokens if t.status is not TokenStatus.DELETION)
        assert from_a.split() == a.split()
        assert from_b.split() == b.split()
        assert _text(a_tokens) == a
        assert _text(b_tokens) == b

    @given(st.text(max_size=200), st.text(max_size=200))
    @settings(max_examples=250, deadline=None)
    def test_reconstruction_property(self, a: str, b: str) -> None:
        """However the diff falls out, both witnesses must survive it intact."""
        _, a_tokens, b_tokens = diff_tokens(a, b)
        assert _text(a_tokens) == a
        assert _text(b_tokens) == b

    @given(st.text(max_size=200), st.text(max_size=200))
    @settings(max_examples=150, deadline=None)
    def test_determinism_property(self, a: str, b: str) -> None:
        first = diff_tokens(a, b)
        second = diff_tokens(a, b)
        assert first == second

    @given(st.text(max_size=200), st.text(max_size=200))
    @settings(max_examples=150, deadline=None)
    def test_stream_purity_property(self, a: str, b: str) -> None:
        _, a_tokens, b_tokens = diff_tokens(a, b)
        assert all(t.status is not TokenStatus.INSERTION for t in a_tokens)
        assert all(t.status is not TokenStatus.DELETION for t in b_tokens)
