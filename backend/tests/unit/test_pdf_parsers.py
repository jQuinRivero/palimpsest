"""PDF parser tests.

Fixtures are generated at test time by `tests/pdf_builder.py` rather than
committed as binaries: they stay readable in review, cost nothing to clone, and
avoid a licence audit on a PDF-generation dependency used only by tests.
"""

from __future__ import annotations

import pytest

from app.models.document import BlockKind, SourceFormat
from app.services.ingestion.base import DocumentSource, SourceProbe
from app.services.ingestion.pdf import (
    MalformedPdfError,
    PdfPlumberParser,
    PyPdfParser,
    ScannedDocumentError,
)
from tests.pdf_builder import build_pdf, build_scanned_pdf, prose_page

PARSERS = [PdfPlumberParser, PyPdfParser]


def source_for(data: bytes, filename: str = "witness.pdf") -> DocumentSource:
    return DocumentSource(
        filename=filename,
        media_type="application/pdf",
        size_bytes=len(data),
        data=data,
    )


def probe_for(data: bytes, filename: str = "witness.pdf") -> SourceProbe:
    return SourceProbe(
        filename=filename,
        media_type="application/pdf",
        magic_bytes=data[:8192],
        size_bytes=len(data),
    )


@pytest.mark.parametrize("parser_class", PARSERS, ids=lambda p: p.name)
class TestSharedParserContract:
    def test_claims_pdf_by_magic_bytes(self, parser_class: type) -> None:
        data = build_pdf([prose_page(["Some prose of reasonable length here."])])
        assert parser_class.can_parse(probe_for(data)) is True

    def test_rejects_non_pdf_despite_extension(self, parser_class: type) -> None:
        """A renamed text file must not be claimed as a PDF."""
        probe = SourceProbe(
            filename="fake.pdf",
            media_type="application/pdf",
            magic_bytes=b"It was the best of times",
            size_bytes=24,
        )
        assert parser_class.can_parse(probe) is False

    def test_capabilities_are_honest(self, parser_class: type) -> None:
        caps = parser_class.capabilities()
        assert caps.preserves_page_numbers is True
        assert caps.is_lossy is True
        # No v1 parser is async, networked, or confidence-bearing; those flags
        # are reserved for the OCR seam.
        assert caps.is_async is False
        assert caps.requires_network is False
        assert caps.emits_confidence is False

    def test_extracts_prose(self, parser_class: type) -> None:
        data = build_pdf([prose_page(["It was a long crossing and the waves were grey."])])
        document = parser_class().parse(source_for(data))

        assert document.source_format is SourceFormat.PDF
        assert document.blocks
        assert "long crossing" in document.blocks[0].text
        assert document.metadata.parser_name == parser_class.name

    def test_records_page_numbers(self, parser_class: type) -> None:
        data = build_pdf(
            [
                prose_page(["First page prose here, running on at some length."]),
                prose_page(["Second page prose, also of a reasonable length."]),
            ]
        )
        document = parser_class().parse(source_for(data))
        pages = {block.page for block in document.blocks}
        assert pages == {1, 2}

    def test_scanned_pdf_raises_rather_than_returning_empty(self, parser_class: type) -> None:
        """A scan must fail honestly; an empty document would be a silent lie."""
        with pytest.raises(ScannedDocumentError):
            parser_class().parse(source_for(build_scanned_pdf(3)))

    def test_malformed_pdf_raises(self, parser_class: type) -> None:
        with pytest.raises((MalformedPdfError, ScannedDocumentError)):
            parser_class().parse(source_for(b"%PDF-1.4\ntruncated and broken"))

    def test_line_breaks_are_reflowed(self, parser_class: type) -> None:
        """Typesetter line breaks must not survive into the diff."""
        data = build_pdf(
            [
                prose_page(
                    [
                        "It was a long crossing and the waves were\n"
                        "grey from the first morning to the last day."
                    ]
                )
            ]
        )
        document = parser_class().parse(source_for(data))
        joined = " ".join(block.text for block in document.blocks)
        assert "were grey from" in joined

    def test_dehyphenation_runs(self, parser_class: type) -> None:
        data = build_pdf(
            [prose_page(["It was an unfor-\ntunate crossing of the cold grey water."])]
        )
        document = parser_class().parse(source_for(data))
        joined = " ".join(block.text for block in document.blocks)
        assert "unfortunate" in joined


class TestPdfPlumberSpecifics:
    """Positional analysis is what pdfplumber is chosen for."""

    def test_running_head_becomes_an_artifact(self) -> None:
        """A line repeating in the header band across pages is not prose."""
        pages = []
        for number in range(1, 5):
            lines = [("A TALE OF TWO CITIES", 72, 30.0)]
            lines += prose_page(
                [f"Body prose for page {number} continues at length here."],
                start_top=120,
            )
            lines.append((str(number), 300, 750.0))
            pages.append(lines)

        document = PdfPlumberParser().parse(source_for(build_pdf(pages)))

        artifacts = [b for b in document.blocks if b.kind is BlockKind.ARTIFACT]
        artifact_text = " ".join(b.text for b in artifacts)
        assert artifacts, "running head and folio number should be ARTIFACT blocks"
        assert "TALE OF TWO CITIES" in artifact_text

        body = " ".join(b.text for b in document.blocks if b.kind is not BlockKind.ARTIFACT)
        assert "TALE OF TWO CITIES" not in body

    def test_folio_numbers_are_grouped_despite_differing_digits(self) -> None:
        """`CHAPTER ONE 17` and `CHAPTER ONE 18` are the same running head."""
        pages = []
        for number in range(11, 16):
            lines = [(f"CHAPTER ONE {number}", 72, 30.0)]
            lines += prose_page([f"Prose body number {number} runs on."], start_top=120)
            pages.append(lines)

        document = PdfPlumberParser().parse(source_for(build_pdf(pages)))
        artifacts = [b for b in document.blocks if b.kind is BlockKind.ARTIFACT]
        assert len(artifacts) >= 3

    def test_short_document_does_not_invent_artifacts(self) -> None:
        """Two pages is not enough evidence to call a line a running head."""
        pages = [
            prose_page(["A single paragraph of ordinary prose on this page."]),
            prose_page(["A different paragraph of ordinary prose here."]),
        ]
        document = PdfPlumberParser().parse(source_for(build_pdf(pages)))
        assert all(b.kind is not BlockKind.ARTIFACT for b in document.blocks)

    def test_paragraph_gaps_split_blocks(self) -> None:
        data = build_pdf(
            [
                prose_page(
                    [
                        "The first paragraph runs along for a while here\n"
                        "and continues onto a second line of its own.",
                        "The second paragraph begins after a wider gap\n"
                        "and likewise runs to a second line.",
                    ]
                )
            ]
        )
        document = PdfPlumberParser().parse(source_for(data))
        body = [b for b in document.blocks if b.kind is not BlockKind.ARTIFACT]
        assert len(body) == 2
        assert "first paragraph" in body[0].text
        assert "second paragraph" in body[1].text

    def test_page_break_does_not_split_a_sentence(self) -> None:
        """A sentence routinely runs across a page break."""
        pages = [
            prose_page(["The sentence begins on the first page and"]),
            prose_page(["continues onto the second page without pause."]),
        ]
        document = PdfPlumberParser().parse(source_for(build_pdf(pages)))
        joined = " ".join(b.text for b in document.blocks)
        assert "first page and continues onto" in joined


class TestParserAgreement:
    def test_both_parsers_recover_the_same_words(self) -> None:
        """They differ in fidelity, not in what the text says."""
        data = build_pdf(
            [
                prose_page(
                    [
                        "It was the best of times, it was the worst of times.",
                        "It was the age of wisdom and of foolishness both.",
                    ]
                )
            ]
        )
        plumber = PdfPlumberParser().parse(source_for(data))
        pypdf = PyPdfParser().parse(source_for(data))

        plumber_words = " ".join(b.text for b in plumber.blocks).split()
        pypdf_words = " ".join(b.text for b in pypdf.blocks).split()
        assert plumber_words == pypdf_words
