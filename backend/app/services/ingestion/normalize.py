"""Canonical text normalization for ingestion."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.models.document import (
    Block,
    BlockKind,
    Document,
    DocumentMetadata,
    IngestionWarning,
    SourceFormat,
)
from app.models.identifiers import block_id
from app.services.ingestion.dehyphenate import Decision, dehyphenate
from app.services.ingestion.reflow import fold_ligatures, looks_like_verse, reflow

_BLANK_LINE = re.compile(r"\n[ \t]*\n+")
_SPACE_RUN = re.compile(r"[ \t]+")

#: C0 controls that XML 1.0 forbids outright. Its Char production admits only
#: tab, newline and carriage return below U+0020, and there is no escape for
#: the rest — not even a numeric reference. A NUL or an ESC that reaches the
#: canonical text therefore travels intact into the TEI export, which is built
#: with ElementTree and serialises without complaint, and the researcher
#: receives an archive no XML parser will open. Form feed is excluded here
#: because it is handled as a break rather than deleted; see _normalize_text.
_FORBIDDEN_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")

#: Emitted when characters were deleted outright. Line-ending and form-feed
#: normalization are not warned about because they preserve the text and only
#: restate the break; deletion loses something, so it is announced.
CONTROL_CHARACTER_WARNING = "CONTROL_CHARACTERS_REMOVED"

#: Emitted when a line-ending hyphen was closed up. A preserved hyphen changes
#: nothing and needs no warning; a join alters the text, so the researcher is
#: told and can see why. See docs/12-edge-cases.md.
DEHYPHENATION_WARNING = "DEHYPHENATION_APPLIED"

#: Verse is exempt from reflow because in poetry the line break is the meaning.
_REFLOW_EXEMPT_KINDS = frozenset({BlockKind.VERSE_LINE, BlockKind.ARTIFACT})

#: Emitted when a block was segmented into verse lines. Segmentation changes
#: the unit of comparison from the stanza to the line, so it is never silent:
#: a researcher must be able to see that the tool decided their prose was a
#: poem. See docs/03-normalization.md.
VERSE_WARNING = "VERSE_SEGMENTED"


@dataclass(frozen=True, slots=True)
class NormalizationBlock:
    """Parser-provided block candidate before canonical offsets are assigned."""

    text: str
    kind: BlockKind = BlockKind.PARAGRAPH
    style: str | None = None
    page: int | None = None
    confidence: float | None = None
    starts_stanza: bool = False


@dataclass(frozen=True, slots=True)
class _Provenance:
    """Where a document came from.

    These five travel together everywhere and are overridden as a set when the
    source is already a ``Document``, so they are carried as one value rather
    than five parallel locals.
    """

    document_id: str
    title: str
    source_format: SourceFormat
    parser_name: str
    parser_version: str


@dataclass(slots=True)
class _SegmentationCounts:
    """What segmentation did, so it can be reported rather than assumed."""

    joins: int = 0
    verse_passages: int = 0
    verse_lines: int = 0


def _coerce_source(
    source: str | Document | list[NormalizationBlock],
    provenance: _Provenance,
    warnings: list[IngestionWarning],
) -> tuple[list[NormalizationBlock], _Provenance, list[IngestionWarning], str]:
    """Reduce the three accepted input shapes to one.

    Also returns the text as it arrived, because the control-character check
    has to run against that rather than against the normalized result —
    normalization is what removes them.
    """
    if isinstance(source, Document):
        # A parsed document already knows its own provenance and warnings, and
        # they win: re-normalizing must not relabel a witness.
        return (
            [
                NormalizationBlock(
                    text=block.text,
                    kind=block.kind,
                    style=block.style,
                    page=block.page,
                    confidence=block.confidence,
                    starts_stanza=block.starts_stanza,
                )
                for block in source.blocks
            ],
            _Provenance(
                document_id=source.id,
                title=source.title,
                source_format=source.source_format,
                parser_name=source.metadata.parser_name,
                parser_version=source.metadata.parser_version,
            ),
            list(source.warnings),
            "\n".join(block.text for block in source.blocks),
        )

    if isinstance(source, str):
        candidates = [
            NormalizationBlock(text=part) for part in _split_blocks(_normalize_text(source))
        ]
        return candidates, provenance, warnings, source

    return source, provenance, warnings, "\n".join(candidate.text for candidate in source)


def _segment(
    candidates: list[NormalizationBlock],
    *,
    reflow_lines: bool,
    corpus: str,
) -> tuple[list[NormalizationBlock], _SegmentationCounts]:
    """Normalize each candidate and split it into the blocks that get compared."""
    segmented: list[NormalizationBlock] = []
    counts = _SegmentationCounts()

    for candidate in candidates:
        normalized_text = _normalize_text(candidate.text)

        # Ligatures are a rendering artefact, never authorial, so they fold
        # unconditionally and before anything that inspects word shape.
        normalized_text = fold_ligatures(normalized_text)

        if reflow_lines and candidate.kind not in _REFLOW_EXEMPT_KINDS:
            # Dehyphenation runs before reflow: it needs the line breaks that
            # reflow is about to remove.
            normalized_text, decisions = dehyphenate(
                normalized_text, join_by_default=True, corpus=corpus
            )
            counts.joins += sum(1 for d in decisions if d.decision is Decision.JOINED)
            normalized_text = reflow(normalized_text)
            normalized_text = _normalize_text(normalized_text)

        for text in _split_blocks(normalized_text):
            kind = _assign_kind(candidate)
            lines = _verse_lines(text) if kind is BlockKind.PARAGRAPH else None

            if lines is None:
                segmented.append(
                    NormalizationBlock(
                        text=text,
                        kind=kind,
                        style=candidate.style,
                        page=candidate.page,
                        confidence=candidate.confidence,
                    )
                )
                continue

            # One block per line. In poetry the line is the unit a scholar
            # compares, so a stanza-sized block would report a single changed
            # word as a wholly modified stanza and would hide a transposed line
            # entirely — moves are detected between blocks, never inside one.
            counts.verse_passages += 1
            counts.verse_lines += len(lines)
            for position, line in enumerate(lines):
                segmented.append(
                    NormalizationBlock(
                        text=line,
                        kind=BlockKind.VERSE_LINE,
                        style=candidate.style,
                        page=candidate.page,
                        confidence=candidate.confidence,
                        # The candidate is one stanza, because candidates are
                        # separated by blank lines. Its first line is therefore
                        # where the stanza begins, and this is the last point at
                        # which that is knowable — after segmentation the blank
                        # line is gone. See ADR-0007.
                        starts_stanza=position == 0,
                    )
                )

    return segmented, counts


def _segmentation_warnings(counts: _SegmentationCounts) -> list[IngestionWarning]:
    """Announce the two decisions that changed the text or the unit of comparison."""
    warnings: list[IngestionWarning] = []

    if counts.joins:
        warnings.append(
            IngestionWarning(
                code=DEHYPHENATION_WARNING,
                message=(
                    f"Closed up {counts.joins} line-ending "
                    f"{'hyphen' if counts.joins == 1 else 'hyphens'} broken across lines. "
                    "Hyphens with evidence of being part of the word were preserved."
                ),
                block_id=None,
            )
        )

    if counts.verse_passages:
        warnings.append(
            IngestionWarning(
                code=VERSE_WARNING,
                message=(
                    f"Read {counts.verse_passages} "
                    f"{'passage' if counts.verse_passages == 1 else 'passages'} as verse and "
                    f"segmented {counts.verse_lines} lines. Each line is compared "
                    "separately; if this text is prose, its blocks have been split "
                    "more finely than intended."
                ),
                block_id=None,
            )
        )

    return warnings


def _build_blocks(segmented: list[NormalizationBlock], witness: str) -> list[Block]:
    """Assign ids and character offsets into the reconstructed full text.

    Offsets assume blocks are rejoined with a blank line, which is what
    ``Document.full_text`` does; the two must not drift apart.
    """
    blocks: list[Block] = []
    offset = 0
    for index, candidate in enumerate(segmented):
        if index:
            offset += 2
        blocks.append(
            Block(
                id=block_id(witness, index),
                index=index,
                kind=candidate.kind,
                text=candidate.text,
                style=candidate.style,
                page=candidate.page,
                char_start=offset,
                char_end=offset + len(candidate.text),
                starts_stanza=candidate.starts_stanza,
                confidence=candidate.confidence,
                bbox=None,
            )
        )
        offset += len(candidate.text)
    return blocks


def normalize(
    source: str | Document | list[NormalizationBlock],
    *,
    document_id: str = "doc_normalized",
    title: str = "Untitled",
    source_format: SourceFormat = SourceFormat.TXT,
    parser_name: str = "normalizer",
    parser_version: str = "1",
    warnings: list[IngestionWarning] | None = None,
    witness: str = "a",
    reflow_lines: bool = False,
) -> Document:
    """Return a deterministic, idempotent canonical ``Document``.

    String input is segmented on blank lines and assigned ``PARAGRAPH`` kind.
    ``Document`` input preserves provenance, warnings, and existing structural
    kind hints while recalculating normalized text, offsets, ids, and metadata.

    ``reflow_lines`` should be set by parsers whose line breaks are a property
    of the *rendering* rather than the text — PDF above all. Plain text and
    Markdown leave it off, because there the line breaks are the author's own
    """
    provenance = _Provenance(
        document_id=document_id,
        title=title,
        source_format=source_format,
        parser_name=parser_name,
        parser_version=parser_version,
    )

    candidates, provenance, base_warnings, raw_text = _coerce_source(
        source, provenance, list(warnings or [])
    )

    # Checked against the text as it arrived, since normalization is what
    # removes them. The title is checked too: it comes from the upload
    # filename, so it is the one field a researcher never typed and a hostile
    # uploader entirely controls.
    if _FORBIDDEN_CONTROLS.search(raw_text) or _FORBIDDEN_CONTROLS.search(provenance.title):
        base_warnings.append(
            IngestionWarning(
                code=CONTROL_CHARACTER_WARNING,
                message=(
                    "Control characters that cannot be represented in XML were removed, "
                    "so the TEI export stays readable. They usually mean the witness was "
                    "decoded with the wrong encoding."
                ),
                block_id=None,
            )
        )

    # Same-document evidence for dehyphenation is drawn from the whole witness,
    # so a compound written inline in chapter nine can settle an ambiguous
    # line-break hyphen in chapter one.
    corpus = _normalize_text("\n\n".join(candidate.text for candidate in candidates))

    segmented, counts = _segment(candidates, reflow_lines=reflow_lines, corpus=corpus)
    base_warnings.extend(_segmentation_warnings(counts))

    blocks = _build_blocks(segmented, witness)
    full_text = "\n\n".join(block.text for block in blocks)

    return Document(
        id=provenance.document_id,
        title=_normalize_title(provenance.title),
        source_format=provenance.source_format,
        blocks=blocks,
        metadata=DocumentMetadata(
            word_count=len(full_text.split()),
            block_count=len(blocks),
            char_count=len(full_text),
            detected_language=None,
            parser_name=provenance.parser_name,
            parser_version=provenance.parser_version,
            ocr_confidence=None,
        ),
        warnings=base_warnings,
    )


def _normalize_text(text: str) -> str:
    """Normalize Unicode, line endings, control characters, and space runs."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # A form feed is a page break, which in a plain-text witness is a break the
    # author or typesetter meant. It cannot survive as itself — XML 1.0 has no
    # room for it — so it becomes the break it already was rather than being
    # dropped along with the rest.
    text = text.replace("\f", "\n")
    text = _FORBIDDEN_CONTROLS.sub("", text)
    lines = [_SPACE_RUN.sub(" ", line.rstrip(" \t")) for line in text.split("\n")]
    return "\n".join(lines).strip()


def _normalize_title(title: str) -> str:
    """Reduce a title to a single clean line.

    Titles arrive from the upload's filename, which is attacker-controlled and
    never passes through block normalization. It is written into the TEI header,
    so it needs the same guarantee the text has.
    """
    cleaned = _FORBIDDEN_CONTROLS.sub("", unicodedata.normalize("NFC", title))
    return _SPACE_RUN.sub(
        " ", cleaned.replace("\f", " ").replace("\n", " ").replace("\r", " ")
    ).strip()


def _split_blocks(text: str) -> list[str]:
    """Split normalized text into non-empty blank-line-delimited blocks."""
    if not text:
        return []
    return [part.strip() for part in _BLANK_LINE.split(text) if part.strip()]


#: Segmentation demands more evidence than reflow exemption does, because the
#: two decisions fail differently. Wrongly exempting a block from reflow leaves
#: some line breaks in place; wrongly segmenting one shatters a paragraph into
#: a dozen blocks and fills the comparison with structure the author never
#: wrote. A verse line is a phrase, so a run of single words — initials, a
#: column of figures, a bare list — is not verse however consistent it looks.
_MIN_MEDIAN_WORDS_PER_VERSE_LINE = 3


def _verse_lines(text: str) -> list[str] | None:
    """Return the block's lines when it reads as verse, otherwise ``None``.

    The measure test is delegated to ``looks_like_verse``, which is
    deliberately biased toward prose. That bias is the right one here and the
    asymmetry is worth stating: a missed poem leaves the previous behaviour,
    whereas a misjudged paragraph is shattered into blocks that no reader of
    the comparison can tell from real structure.

    A single-line block is never verse. One line carries no evidence of
    consistent measure, and a short standalone line is far more often a
    heading, a speaker label, or a date.
    """
    if "\n" not in text:
        return None

    if not looks_like_verse(text.split("\n")):
        return None

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    counts = sorted(len(line.split()) for line in lines)
    median_words = counts[len(counts) // 2]
    if median_words < _MIN_MEDIAN_WORDS_PER_VERSE_LINE:
        return None

    return lines


def _assign_kind(candidate: NormalizationBlock) -> BlockKind:
    """Return the structural kind supplied by the parser candidate."""
    return candidate.kind
