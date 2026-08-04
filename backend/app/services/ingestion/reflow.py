"""Soft line-break reflow and ligature folding.

A PDF breaks lines for layout, not for meaning. Left alone, those breaks become
part of the text and every one of them shows up as a difference the author
never made. Reflow joins them back into continuous prose.

Verse is the counter-case and the reason this cannot simply join everything: in
poetry and drama the line break *is* the meaning. ``VERSE_LINE`` blocks are
exempt, and short-line runs are detected and left alone even when the parser
did not classify them.

See docs/03-normalization.md and docs/12-edge-cases.md.
"""

from __future__ import annotations

import statistics

#: Typographic ligatures are an artefact of rendering, not of authorship: no
#: writer chose U+FB01 over "fi". Folding them is always correct and is not
#: exposed as an option. Curly quotes and dashes are deliberately NOT folded
#: here — a scholar studying compositor practice cares about ' versus ', so
#: that belongs to DiffOptions, not to ingestion.
LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
    "\u0132": "IJ",
    "\u0133": "ij",
    "\u0152": "OE",
    "\u0153": "oe",
    "\u00c6": "AE",
    "\u00e6": "ae",
}

_LIGATURE_TABLE = str.maketrans(LIGATURES)

#: A line shorter than this fraction of the block's median is treated as
#: deliberately short — a verse line, a heading, or the end of a stanza.
SHORT_LINE_RATIO = 0.55

#: Below this many lines there is no reliable median to reason about, so
#: reflow proceeds without the short-line check.
MIN_LINES_FOR_MEDIAN = 4

#: Verse detection from text alone is genuinely hard, so this is deliberately
#: conservative: only lines well below any normal prose measure qualify. The
#: reliable signal is the parser setting ``BlockKind.VERSE_LINE``, which is
#: exempted from reflow outright; this heuristic is only a backstop for
#: parsers that cannot tell. Erring toward "prose" means a genuinely versified
#: block might be reflowed, but erring the other way leaves typesetter line
#: breaks throughout every PDF, which produces phantom differences on every
#: line of a comparison.
MAX_VERSE_MEDIAN = 45


def fold_ligatures(text: str) -> str:
    """Replace typographic ligatures with their component letters."""
    return text.translate(_LIGATURE_TABLE)


def looks_like_verse(lines: list[str]) -> bool:
    """Whether a run of lines reads as verse rather than reflowed prose.

    Two properties together distinguish verse: the lines are *short* relative
    to any normal prose measure, and they are *consistently* short. Prose
    broken by a typesetter is also consistent — it sits near the measure — so
    consistency alone is not enough, and using it alone misclassifies a
    narrow-column prose PDF as poetry.
    """
    meaningful = [line for line in lines if line.strip()]
    if len(meaningful) < 3:
        return False

    lengths = [len(line) for line in meaningful]
    median = statistics.median(lengths)
    if median == 0:
        return False

    # Verse sits well below a prose measure. This is the load-bearing test.
    if median > MAX_VERSE_MEDIAN:
        return False

    # Ignore the last line: a short final line is normal in prose too.
    short = sum(1 for length in lengths[:-1] if length < median * SHORT_LINE_RATIO)
    if short:
        return False

    spread = max(lengths) - min(lengths)
    return spread < median * 0.6


def reflow(text: str) -> str:
    """Join lines that were broken for layout, preserving paragraph structure.

    Operates within a single block; blank-line paragraph separation has already
    been handled by segmentation.
    """
    lines = text.split("\n")
    if len(lines) < 2:
        return text

    if looks_like_verse(lines):
        return text

    lengths = [len(line) for line in lines if line.strip()]
    median = statistics.median(lengths) if len(lengths) >= MIN_LINES_FOR_MEDIAN else None

    joined: list[str] = []
    for position, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if not joined:
            joined.append(stripped)
            continue

        previous = joined[-1]

        # A markedly short preceding line was short on purpose — the end of a
        # stanza, a heading, or a speaker label — so do not pull the next line
        # up onto it. The final line is exempt: prose ends short too.
        if (
            median is not None
            and position < len(lines)
            and len(previous) < median * SHORT_LINE_RATIO
        ):
            joined.append(stripped)
            continue

        joined[-1] = f"{previous} {stripped}"

    return "\n".join(joined)
