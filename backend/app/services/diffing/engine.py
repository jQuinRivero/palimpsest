"""Word-level diffing — stage 2 of the engine.

``diff-match-patch`` diffs *characters*. Applied naively to prose it reports
``sat`` versus ``set`` as an equality, a deletion, an insertion and an equality
inside a single word, which is visually intolerable in long-form reading and
wrong for textual scholarship. What we want is word-level output.

The library ships the machinery for this in ``diff_linesToChars`` and
``diff_charsToLines``: map each unique line to a single code point, diff the
compact strings, map back. The technique is not restricted to lines — it works
for any tokenization, and we apply it at word granularity.

Retaining access to those helpers is precisely why ADR-0001 selects the pure
Python community fork over the faster C++ binding, whose simplified API omits
them.

See docs/04-diff-engine.md.
"""

from __future__ import annotations

from diff_match_patch import diff_match_patch

from app.models.diff import DiffOptions, Token, TokenStatus
from app.services.diffing.tokenizer import comparison_key, tokenize

#: diff-match-patch operation constants.
_DELETE = -1
_INSERT = 1
_EQUAL = 0
_SEPARATOR = " "

#: One code point per unique token type. The ceiling is the Unicode range; a
#: 100k-word English manuscript has on the order of 10-20k distinct types, so
#: this is not a practical limit — but exceeding it must fail loudly rather
#: than silently corrupt output.
_MAX_VOCABULARY = 1_114_111


class DiffBudgetExceeded(Exception):
    """The comparison is too large to diff. Maps to ``DIFF_BUDGET_EXCEEDED``."""


class _Vocabulary:
    """Bidirectional map between token comparison keys and code points."""

    def __init__(self) -> None:
        self._to_char: dict[str, str] = {}

    def encode(self, tokens: list[str], options: DiffOptions) -> str:
        chars: list[str] = []
        for token in tokens:
            key = comparison_key(token, options)
            char = self._to_char.get(key)
            if char is None:
                if len(self._to_char) >= _MAX_VOCABULARY:
                    raise DiffBudgetExceeded(
                        f"vocabulary exceeded {_MAX_VOCABULARY} distinct tokens"
                    )
                # Skip the surrogate range: those code points cannot round-trip
                # through Python strings safely.
                index = len(self._to_char) + 1
                if 0xD800 <= index <= 0xDFFF:
                    index += 0x800
                char = chr(index)
                self._to_char[key] = char
            chars.append(char)
        return "".join(chars)


def _separate(pieces: list[tuple[TokenStatus, str]]) -> list[tuple[TokenStatus, str]]:
    """Ensure adjacent runs in the unified stream cannot fuse into one word.

    The unified stream interleaves all three statuses, so two runs that were
    never adjacent in either witness end up side by side. When the earlier one
    ends without whitespace — because it ended a block, or ended a witness —
    concatenation glues it to the next: "alpha" + "beta" reads "alphabeta".

    Only the unified stream needs this. ``a_tokens`` and ``b_tokens`` reproduce
    their own witness verbatim and must never be touched.
    """
    out: list[tuple[TokenStatus, str]] = []
    for status, text in pieces:
        if not text:
            continue
        if out:
            previous_status, previous_text = out[-1]
            if previous_text and not previous_text[-1].isspace() and not text[0].isspace():
                # The separator joins the earlier run. Word sequences are
                # unaffected, so both projections still agree with their pane.
                out[-1] = (previous_status, previous_text + " ")
        out.append((status, text))
    return out


def _coalesce(pieces: list[tuple[TokenStatus, str]]) -> list[Token]:
    """Merge adjacent same-status runs into single ``Token`` objects.

    A payload ``Token`` carries a contiguous run rather than one word: emitting
    one object per word would triple the payload and produce one DOM node per
    word for no reader-visible benefit, since adjacent words of identical
    status render identically anyway.
    """
    merged: list[Token] = []
    for status, text in pieces:
        if not text:
            continue
        if merged and merged[-1].status is status:
            merged[-1] = Token(text=merged[-1].text + text, status=status)
        else:
            merged.append(Token(text=text, status=status))
    return merged


def diff_tokens(
    a_text: str,
    b_text: str,
    options: DiffOptions | None = None,
) -> tuple[list[Token], list[Token], list[Token]]:
    """Diff two block texts at word granularity.

    Returns ``(tokens, a_tokens, b_tokens)``:

    * ``tokens`` is the unified stream, interleaving all three statuses.
    * ``a_tokens`` is ``UNCHANGED`` + ``DELETION`` — the Manuscript A pane.
    * ``b_tokens`` is ``UNCHANGED`` + ``INSERTION`` — the Manuscript B pane.

    All three are derived from one diff. They are computed here rather than on
    the client because filtering is cheap but getting it wrong is a subtle
    rendering bug, and because it keeps the client a pure renderer (ADR-0004).
    """
    options = options or DiffOptions()

    a_tokens_raw = tokenize(a_text, options.granularity)
    b_tokens_raw = tokenize(b_text, options.granularity)

    vocabulary = _Vocabulary()
    a_encoded = vocabulary.encode(a_tokens_raw, options)
    b_encoded = vocabulary.encode(b_tokens_raw, options)

    dmp = diff_match_patch()
    # checklines is a line-oriented speedup that is meaningless once we have
    # already remapped to a word alphabet.
    diffs = dmp.diff_main(a_encoded, b_encoded, False)

    # Coalesces small scattered edits into larger human-meaningful ones, which
    # is what a reader wants. diff_cleanupEfficiency is deliberately NOT applied:
    # it optimises for patch size, and we never produce patches.
    dmp.diff_cleanupSemantic(diffs)

    unified: list[tuple[TokenStatus, str]] = []
    a_stream: list[tuple[TokenStatus, str]] = []
    b_stream: list[tuple[TokenStatus, str]] = []

    a_pos = 0
    b_pos = 0

    for op, chunk in diffs:
        length = len(chunk)
        if op == _EQUAL:
            a_run = "".join(a_tokens_raw[a_pos : a_pos + length])
            b_run = "".join(b_tokens_raw[b_pos : b_pos + length])
            # Each pane keeps its own witness verbatim, so a_tokens and
            # b_tokens always reconstruct exactly. The unified stream carries
            # Manuscript A's reading, which is the earlier one.
            unified.append((TokenStatus.UNCHANGED, a_run))
            a_stream.append((TokenStatus.UNCHANGED, a_run))
            b_stream.append((TokenStatus.UNCHANGED, b_run))
            a_pos += length
            b_pos += length
        elif op == _DELETE:
            text = "".join(a_tokens_raw[a_pos : a_pos + length])
            unified.append((TokenStatus.DELETION, text))
            a_stream.append((TokenStatus.DELETION, text))
            a_pos += length
        else:
            text = "".join(b_tokens_raw[b_pos : b_pos + length])
            unified.append((TokenStatus.INSERTION, text))
            b_stream.append((TokenStatus.INSERTION, text))
            b_pos += length

    # Separation is applied once, to the unified stream only. The pane streams
    # must stay byte-exact reproductions of their witnesses.
    return _coalesce(_separate(unified)), _coalesce(a_stream), _coalesce(b_stream)
