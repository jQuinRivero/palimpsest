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
    and joining them would be a fabrication.
    """
    base_warnings = list(warnings or [])
    candidates: list[NormalizationBlock]

    if isinstance(source, Document):
        document_id = source.id
        title = source.title
        source_format = source.source_format
        parser_name = source.metadata.parser_name
        parser_version = source.metadata.parser_version
        base_warnings = list(source.warnings)
        candidates = [
            NormalizationBlock(
                text=block.text,
                kind=block.kind,
                style=block.style,
                page=block.page,
                confidence=block.confidence,
            )
            for block in source.blocks
        ]
    elif isinstance(source, str):
        candidates = [
            NormalizationBlock(text=part) for part in _split_blocks(_normalize_text(source))
        ]
    else:
        candidates = source

    normalized_blocks: list[NormalizationBlock] = []
    join_count = 0
    verse_passages = 0
    verse_line_count = 0

    # Same-document evidence for dehyphenation is drawn from the whole witness,
    # so a compound written inline in chapter nine can settle an ambiguous
    # line-break hyphen in chapter one.
    corpus = _normalize_text("\n\n".join(candidate.text for candidate in candidates))

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
            join_count += sum(1 for d in decisions if d.decision is Decision.JOINED)
            normalized_text = reflow(normalized_text)
            normalized_text = _normalize_text(normalized_text)

        for text in _split_blocks(normalized_text):
            kind = _assign_kind(candidate)
            lines = _verse_lines(text) if kind is BlockKind.PARAGRAPH else None

            if lines is not None:
                # One block per line. In poetry the line is the unit a scholar
                # compares, so a stanza-sized block would report a single
                # changed word as a wholly modified stanza and would hide a
                # transposed line entirely — moves are detected between
                # blocks, never inside one.
                verse_passages += 1
                verse_line_count += len(lines)
                for line in lines:
                    normalized_blocks.append(
                        NormalizationBlock(
                            text=line,
                            kind=BlockKind.VERSE_LINE,
                            style=candidate.style,
                            page=candidate.page,
                            confidence=candidate.confidence,
                        )
                    )
                continue

            normalized_blocks.append(
                NormalizationBlock(
                    text=text,
                    kind=kind,
                    style=candidate.style,
                    page=candidate.page,
                    confidence=candidate.confidence,
                )
            )

    if join_count:
        base_warnings.append(
            IngestionWarning(
                code=DEHYPHENATION_WARNING,
                message=(
                    f"Closed up {join_count} line-ending "
                    f"{'hyphen' if join_count == 1 else 'hyphens'} broken across lines. "
                    "Hyphens with evidence of being part of the word were preserved."
                ),
                block_id=None,
            )
        )

    if verse_passages:
        base_warnings.append(
            IngestionWarning(
                code=VERSE_WARNING,
                message=(
                    f"Read {verse_passages} "
                    f"{'passage' if verse_passages == 1 else 'passages'} as verse and "
                    f"segmented {verse_line_count} lines. Each line is compared "
                    "separately; if this text is prose, its blocks have been split "
                    "more finely than intended."
                ),
                block_id=None,
            )
        )

    blocks: list[Block] = []
    offset = 0
    for index, candidate in enumerate(normalized_blocks):
        if index:
            offset += 2
        text = candidate.text
        blocks.append(
            Block(
                id=block_id(witness, index),
                index=index,
                kind=candidate.kind,
                text=text,
                style=candidate.style,
                page=candidate.page,
                char_start=offset,
                char_end=offset + len(text),
                confidence=candidate.confidence,
                bbox=None,
            )
        )
        offset += len(text)

    full_text = "\n\n".join(block.text for block in blocks)
    metadata = DocumentMetadata(
        word_count=len(full_text.split()),
        block_count=len(blocks),
        char_count=len(full_text),
        detected_language=None,
        parser_name=parser_name,
        parser_version=parser_version,
        ocr_confidence=None,
    )

    return Document(
        id=document_id,
        title=title,
        source_format=source_format,
        blocks=blocks,
        metadata=metadata,
        warnings=base_warnings,
    )


def _normalize_text(text: str) -> str:
    """Normalize Unicode, line endings, trailing whitespace, and space runs."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACE_RUN.sub(" ", line.rstrip(" \t")) for line in text.split("\n")]
    return "\n".join(lines).strip()


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
