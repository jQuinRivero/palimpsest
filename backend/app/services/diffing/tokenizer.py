"""Tokenization.

The unit of diffing is the token. Under ``Granularity.WORD`` a token is a run of
non-whitespace characters together with the whitespace that follows it.

Carrying the trailing whitespace inside the token matters more than it appears
to: it means the concatenation of a block's tokens reproduces the block's text
exactly, with no separator bookkeeping and no lost spacing. That reconstruction
property is asserted as an invariant throughout the test suite.

See docs/04-diff-engine.md.
"""

from __future__ import annotations

import re
import unicodedata

from app.models.diff import DiffOptions, Granularity

#: A run of non-whitespace followed by its trailing whitespace.
_WORD_TOKEN = re.compile(r"\S+\s*")


def tokenize(text: str, granularity: Granularity = Granularity.WORD) -> list[str]:
    """Split ``text`` into tokens whose concatenation reproduces ``text``.

    ``CHARACTER`` granularity is appropriate for scripts without word
    separators and for close orthographic study; it is substantially more
    expensive. See docs/12-edge-cases.md on CJK.
    """
    if granularity is Granularity.CHARACTER:
        return list(text)

    tokens = _WORD_TOKEN.findall(text)

    # findall drops any leading whitespace, which would break reconstruction.
    if tokens:
        consumed = "".join(tokens)
        if len(consumed) != len(text):
            leading = text[: len(text) - len(text.lstrip())]
            if leading:
                tokens[0] = leading + tokens[0]
    elif text:
        # Whitespace-only input is a single token, so that reconstruction holds.
        tokens = [text]

    return tokens


def comparison_key(token: str, options: DiffOptions) -> str:
    """Derive the string used for *comparing* a token.

    Some options change how tokens compare without changing how they render.
    A researcher who enables ``ignore_case`` still sees the manuscript's real
    capitalisation on screen; only this derived key is folded.
    """
    key = token

    if options.normalize_whitespace:
        key = key.strip()

    if options.ignore_case:
        key = key.casefold()

    if options.ignore_punctuation:
        key = "".join(ch for ch in key if not unicodedata.category(ch).startswith("P"))

    return key


def word_count(text: str) -> int:
    """Count words the same way metrics do, so the two never disagree."""
    return len(text.split())
