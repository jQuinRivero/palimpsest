"""TEI P5 export tests.

The load-bearing assertion is reconstruction: selecting every ``<rdg wit="#A">``
and concatenating must reproduce the Manuscript A pane word for word, and the
same for B. That is the property that makes the export an archive rather than a
rendering, and it is asserted with a parser rather than by string matching so
that a change in serialisation cannot quietly pass.

See docs/adr/0006-tei-parallel-segmentation-export.md.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from app.models import BlockKind, BlockStatus, DiffOptions
from app.services.formatting.payload import build_comparison
from app.services.formatting.tei import build_tei
from tests.unit.test_payload import make_document

TEI = "http://www.tei-c.org/ns/1.0"
NS = {"t": TEI}


def tei_for(a: list[str], b: list[str], **kwargs: object) -> tuple[str, ET.Element]:
    comparison = build_comparison(
        make_document("a", a, title="Witness A"),
        make_document("b", b, title="Witness B"),
        DiffOptions(**kwargs) if kwargs else DiffOptions(),
    )
    document = build_tei(comparison)
    return document, ET.fromstring(document)


def reading(element: ET.Element, witness: str) -> str:
    """Reconstruct one witness's text from a block element."""
    if element.tag == f"{{{TEI}}}app":
        for rdg in element:
            if rdg.get("wit") == f"#{witness}":
                return rdg.text or ""
        return ""

    parts = [element.text or ""]
    for child in element:
        parts.append(reading(child, witness))
        parts.append(child.tail or "")
    return "".join(parts)


def panes(root: ET.Element, witness: str) -> list[str]:
    body = root.find("t:text/t:body", NS)
    assert body is not None
    return [reading(block, witness) for block in body]


class TestReconstruction:
    """Both witnesses must survive the round trip through TEI."""

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            pytest.param(["Identical prose here."], ["Identical prose here."], id="identical"),
            pytest.param(
                ["The waves were grey that morning."],
                ["The waves were slate that morning."],
                id="substitution",
            ),
            pytest.param(["Kept."], ["Kept.", "Added paragraph."], id="insertion"),
            pytest.param(["Kept.", "Removed paragraph."], ["Kept."], id="deletion"),
            pytest.param(
                ["It was a long crossing. The waves were grey."],
                ["It was a long crossing.", "The waves were grey."],
                id="split",
            ),
            pytest.param(
                ["It was a long crossing.", "The waves were grey."],
                ["It was a long crossing. The waves were grey."],
                id="merge",
            ),
            pytest.param(
                ["Alpha stands first.", "Beta follows it.", "Gamma ends it."],
                ["Gamma ends it.", "Alpha stands first.", "Beta follows it."],
                id="move",
            ),
            pytest.param(
                ["Entirely different opening text."],
                ["Nothing whatsoever in common."],
                id="unrelated",
            ),
        ],
    )
    def test_each_witness_round_trips(self, a: list[str], b: list[str]) -> None:
        comparison = build_comparison(
            make_document("a", a, title="Witness A"),
            make_document("b", b, title="Witness B"),
        )
        root = ET.fromstring(build_tei(comparison))

        for witness, attribute in (("A", "a_tokens"), ("B", "b_tokens")):
            expected = [
                "".join(token.text for token in getattr(block, attribute))
                for block in comparison.blocks
            ]
            assert panes(root, witness) == expected, f"witness {witness} did not round trip"

    def test_indentation_never_enters_a_reading(self) -> None:
        """Pretty-printing must not add whitespace inside a block.

        The failure this guards is subtle: a block whose first token is a
        change has no leading text, and a naive indenter fills that slot with
        a newline. The document still parses and still looks right, but every
        such reading has acquired whitespace the witness never had.
        """
        _, root = tei_for(
            ["Changed opening word survives."],
            ["Altered opening word survives."],
        )
        body = root.find("t:text/t:body", NS)
        assert body is not None
        block = body[0]

        assert block.text is None or not block.text.startswith("\n")
        for child in block.iter():
            if child is block:
                continue
            assert "\n" not in (child.text or "")
            assert "\n" not in (child.tail or "")


class TestStructure:
    def test_declares_parallel_segmentation(self) -> None:
        _, root = tei_for(["One."], ["Two."])
        encoding = root.find("t:teiHeader/t:encodingDesc/t:variantEncoding", NS)
        assert encoding is not None
        assert encoding.get("method") == "parallel-segmentation"
        assert encoding.get("location") == "internal"

    def test_lists_both_witnesses_with_ids(self) -> None:
        _, root = tei_for(["One."], ["Two."])
        witnesses = root.findall("t:teiHeader/t:fileDesc/t:sourceDesc/t:listWit/t:witness", NS)
        ids = [w.get("{http://www.w3.org/XML/1998/namespace}id") for w in witnesses]
        assert ids == ["A", "B"]
        assert "Witness A" in (witnesses[0].text or "")
        assert "Witness B" in (witnesses[1].text or "")

    def test_every_block_carries_a_stable_id(self) -> None:
        comparison = build_comparison(
            make_document("a", ["Alpha.", "Beta."]),
            make_document("b", ["Alpha.", "Gamma."]),
        )
        root = ET.fromstring(build_tei(comparison))
        body = root.find("t:text/t:body", NS)
        assert body is not None

        ids = [b.get("{http://www.w3.org/XML/1998/namespace}id") for b in body]
        assert ids == [f"blk-{block.id}" for block in comparison.blocks]
        assert len(set(ids)) == len(ids)

    def test_omission_is_an_empty_reading_not_a_missing_one(self) -> None:
        """A witness that omits a passage must still be collated there."""
        _, root = tei_for(["Kept."], ["Kept.", "Only in B."])
        apps = root.findall(".//t:app", NS)
        assert apps, "an inserted block should produce an apparatus entry"

        for app in apps:
            wits = [rdg.get("wit") for rdg in app]
            assert wits == ["#A", "#B"], "both witnesses must appear in every entry"

    @pytest.mark.parametrize(
        ("kind", "expected"),
        [
            (BlockKind.PARAGRAPH, "p"),
            (BlockKind.HEADING, "head"),
            (BlockKind.VERSE_LINE, "l"),
            (BlockKind.QUOTE, "quote"),
            (BlockKind.LIST_ITEM, "item"),
            (BlockKind.ARTIFACT, "fw"),
        ],
    )
    def test_block_kind_maps_to_a_tei_element(self, kind: BlockKind, expected: str) -> None:
        doc_a = make_document("a", ["Some text here."])
        doc_b = make_document("b", ["Some text here."])
        for document in (doc_a, doc_b):
            document.blocks[0].kind = kind

        root = ET.fromstring(build_tei(build_comparison(doc_a, doc_b)))
        body = root.find("t:text/t:body", NS)
        assert body is not None
        assert body[0].tag == f"{{{TEI}}}{expected}"


class TestStructuralRelations:
    def test_a_move_is_linked_in_the_back_matter(self) -> None:
        comparison = build_comparison(
            make_document("a", ["Alpha stands first.", "Beta follows it.", "Gamma ends it."]),
            make_document("b", ["Gamma ends it.", "Alpha stands first.", "Beta follows it."]),
        )
        moved = [b for b in comparison.blocks if b.status is BlockStatus.MOVED]
        assert moved, "fixture should produce a move"

        root = ET.fromstring(build_tei(comparison))
        group = root.find("t:text/t:back/t:linkGrp[@type='moved']", NS)
        assert group is not None

        targets = {link.get("target") for link in group}
        assert {f"#blk-{block.id}" for block in moved} == targets

    def test_a_split_links_its_members_together(self) -> None:
        comparison = build_comparison(
            make_document("a", ["It was a long crossing. The waves were grey."]),
            make_document("b", ["It was a long crossing.", "The waves were grey."]),
        )
        members = [b for b in comparison.blocks if b.status is BlockStatus.SPLIT]
        assert len(members) == 2, "fixture should produce a two-member split"

        root = ET.fromstring(build_tei(comparison))
        group = root.find("t:text/t:back/t:linkGrp[@type='split']", NS)
        assert group is not None

        links = list(group)
        assert len(links) == 1, "one split is one link, not one link per member"
        assert (links[0].get("target") or "").split() == [f"#blk-{block.id}" for block in members]

    def test_unchanged_comparison_has_no_back_matter(self) -> None:
        _, root = tei_for(["Same text."], ["Same text."])
        assert root.find("t:text/t:back", NS) is None


class TestSafety:
    def test_markup_in_the_manuscript_is_escaped(self) -> None:
        """A witness containing angle brackets must not become markup."""
        hostile = "A <rdg> & an ]]> in the prose."
        document, root = tei_for([hostile], [hostile])

        assert "<rdg>" not in document.replace("<rdg ", "")
        assert "&amp;" in document
        assert panes(root, "A") == [hostile]

    def test_windowed_comparison_is_refused(self) -> None:
        comparison = build_comparison(
            make_document("a", ["Alpha.", "Beta."]),
            make_document("b", ["Alpha.", "Gamma."]),
        )
        windowed = comparison.model_copy(update={"truncated": True})

        with pytest.raises(ValueError, match="windowed"):
            build_tei(windowed)

    def test_metrics_are_reported_in_the_header(self) -> None:
        _, root = tei_for(["The waves were grey."], ["The waves were slate."])
        prose = root.find("t:teiHeader/t:encodingDesc/t:p", NS)
        assert prose is not None
        text = prose.text or ""

        # Singular for one, plural for the rest. Getting this wrong reads as
        # sloppy in a document a scholar may quote from.
        assert "1 word inserted" in text
        assert "1 word deleted" in text
        assert "3 words unchanged" in text
        assert "0 blocks moved" in text

    def test_document_is_declared_utf8(self) -> None:
        document, _ = tei_for(["Éire — naïve coöperation."], ["Éire — naive cooperation."])
        assert document.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        assert "Éire" in document
