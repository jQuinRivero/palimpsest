"""Dehyphenation: repairing words a typesetter broke across a line.

Three different things look like a hyphen at a line ending, and conflating them
corrupts real text:

* a **hard hyphen** belonging to the word — ``self-evident``, ``well-being``
* a **soft hyphen** inserted purely to justify a line — ``unfor-\\ntunate``
* an **em or en dash** used as punctuation — ``visitor—\\nstill``

The naive rule ``re.sub(r'-\\n(\\w)', r'\\1', text)`` is therefore forbidden.
Applied to ``self-\\nevident`` it yields ``selfevident``, destroying a genuine
compound and inventing a textual variant that the author never wrote — in a
tool whose entire purpose is reporting what changed, that is the worst possible
class of bug.

The policy below is deliberately **conservative**: when the evidence does not
clearly favour joining, the hyphen is preserved, because a spurious hyphen is
visible and diagnosable while a spurious join silently fabricates a word.

Every decision is recorded, so the UI can explain why two passages differ only
in hyphenation. See docs/12-edge-cases.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

#: Only these are candidates for joining. En dash, em dash, horizontal bar and
#: friends are punctuation and are never treated as word-internal hyphenation.
JOINABLE_HYPHENS = ("-", "\u2010", "\u00ad")  # hyphen-minus, hyphen, soft hyphen

#: Punctuation dashes: a line-ending one is reflowed but never closed up.
PUNCTUATION_DASHES = ("\u2013", "\u2014", "\u2015", "\u2212")

#: Prefixes that conventionally keep their hyphen in English. Not exhaustive —
#: it does not need to be, because it only tips genuinely ambiguous cases
#: toward preservation, which is the safe direction.
HYPHENATED_PREFIXES = frozenset(
    {
        "all",
        "anti",
        "co",
        "counter",
        "cross",
        "ex",
        "extra",
        "half",
        "inter",
        "mid",
        "multi",
        "neo",
        "non",
        "over",
        "post",
        "pre",
        "pro",
        "pseudo",
        "quasi",
        "re",
        "self",
        "semi",
        "sub",
        "super",
        "trans",
        "ultra",
        "un",
        "under",
        "well",
    }
)

_LINE_BREAK_HYPHEN = re.compile(
    r"(\w[\w'\u2019]*)([" + "".join(JOINABLE_HYPHENS) + r"])\n(\w[\w'\u2019]*)"
)
_PUNCTUATION_DASH_BREAK = re.compile(r"([" + "".join(PUNCTUATION_DASHES) + r"])\n(?=\w)")
_WORD = re.compile(r"[\w'\u2019]+")


class Decision(StrEnum):
    """What was done with a line-ending hyphen, and on what evidence."""

    #: The two fragments were closed up: ``unfor-\ntunate`` -> ``unfortunate``.
    JOINED = "JOINED"
    #: The hyphen was kept: ``self-\nevident`` -> ``self-evident``.
    PRESERVED = "PRESERVED"


class Evidence(StrEnum):
    """Why the decision went the way it did. Recorded for auditability."""

    #: The hyphenated compound occurs elsewhere in the same witness, away from
    #: a line break. The strongest available signal.
    COMPOUND_SEEN_ELSEWHERE = "COMPOUND_SEEN_ELSEWHERE"
    #: The closed-up form occurs elsewhere in the same witness.
    JOINED_SEEN_ELSEWHERE = "JOINED_SEEN_ELSEWHERE"
    #: The second fragment is itself hyphenated onward — ``mother-in-law``.
    COMPOUND_CHAIN = "COMPOUND_CHAIN"
    #: The second fragment is capitalised — likely a proper compound.
    CAPITALISED_SECOND = "CAPITALISED_SECOND"
    #: A digit is involved; never close up a numeric range or reference.
    NUMERIC = "NUMERIC"
    #: The first fragment is a conventionally hyphenated prefix.
    HYPHENATED_PREFIX = "HYPHENATED_PREFIX"
    #: No evidence either way; the conservative default applied.
    DEFAULT = "DEFAULT"


@dataclass(frozen=True, slots=True)
class DehyphenationDecision:
    """One reversible, explicable decision about one line-ending hyphen."""

    first: str
    second: str
    decision: Decision
    evidence: Evidence

    @property
    def result(self) -> str:
        if self.decision is Decision.JOINED:
            return f"{self.first}{self.second}"
        return f"{self.first}-{self.second}"


def _vocabulary(text: str) -> set[str]:
    """Case-folded words in the witness, for same-document evidence."""
    return {match.group(0).casefold() for match in _WORD.finditer(text)}


def _hyphenated_forms(text: str) -> set[str]:
    """Hyphenated compounds appearing *away from* a line break.

    A compound the author wrote inline elsewhere is strong evidence that the
    same compound broken across a line is genuinely hyphenated.
    """
    forms = set()
    for match in re.finditer(r"(\w[\w'\u2019]*)-(\w[\w'\u2019]*)", text):
        forms.add(f"{match.group(1)}-{match.group(2)}".casefold())
    return forms


def decide(
    first: str,
    second: str,
    *,
    vocabulary: set[str],
    hyphenated: set[str],
    join_by_default: bool,
    chained: bool = False,
) -> DehyphenationDecision:
    """Decide one line-ending hyphen, conservatively.

    ``chained`` means the second fragment is itself followed by a hyphen, as in
    ``mother-\\nin-law``: the compound continues, so closing up the first join
    would produce ``motherin-law``.

    ``join_by_default`` reflects provenance rather than linguistics. In a PDF a
    line-ending hyphen is usually a typesetter's soft hyphen, so joining is the
    better default. In plain text or Markdown the line break is the author's
    own and the hyphen is far more likely to be theirs too, so preservation is
    the better default.
    """
    joined = f"{first}{second}".casefold()
    compound = f"{first}-{second}".casefold()

    def result(decision: Decision, evidence: Evidence) -> DehyphenationDecision:
        return DehyphenationDecision(first, second, decision, evidence)

    # Ordered by strength of evidence.
    if compound in hyphenated:
        return result(Decision.PRESERVED, Evidence.COMPOUND_SEEN_ELSEWHERE)
    if chained:
        return result(Decision.PRESERVED, Evidence.COMPOUND_CHAIN)
    if joined in vocabulary:
        return result(Decision.JOINED, Evidence.JOINED_SEEN_ELSEWHERE)
    if any(ch.isdigit() for ch in first + second):
        return result(Decision.PRESERVED, Evidence.NUMERIC)
    if second[:1].isupper():
        return result(Decision.PRESERVED, Evidence.CAPITALISED_SECOND)
    if first.casefold() in HYPHENATED_PREFIXES:
        return result(Decision.PRESERVED, Evidence.HYPHENATED_PREFIX)

    return result(
        Decision.JOINED if join_by_default else Decision.PRESERVED,
        Evidence.DEFAULT,
    )


def dehyphenate(
    text: str,
    *,
    join_by_default: bool = True,
    corpus: str | None = None,
) -> tuple[str, list[DehyphenationDecision]]:
    """Repair line-ending hyphens in ``text``.

    ``corpus`` supplies the same-document evidence. It defaults to ``text``
    itself, but a caller normalizing block by block should pass the whole
    witness so that evidence from chapter nine can inform chapter one.

    Returns the repaired text and the decisions taken, in order.
    """
    source = corpus if corpus is not None else text
    vocabulary = _vocabulary(source)
    hyphenated = _hyphenated_forms(source)
    decisions: list[DehyphenationDecision] = []

    def replace(match: re.Match[str]) -> str:
        first, _, second = match.group(1), match.group(2), match.group(3)
        # A hyphen immediately after the second fragment means the compound
        # continues: "mother-\nin-law" must not become "motherin-law".
        chained = text[match.end() : match.end() + 1] in ("-", "\u2010")
        outcome = decide(
            first,
            second,
            vocabulary=vocabulary,
            hyphenated=hyphenated,
            join_by_default=join_by_default,
            chained=chained,
        )
        decisions.append(outcome)
        return outcome.result

    repaired = _LINE_BREAK_HYPHEN.sub(replace, text)

    # A punctuation dash at a line ending is reflowed but never closed up:
    # "visitor—\nstill" is two words, not "visitorstill".
    repaired = _PUNCTUATION_DASH_BREAK.sub(r"\1", repaired)

    return repaired, decisions
