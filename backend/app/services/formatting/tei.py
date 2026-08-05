"""TEI P5 export — the collation as a scholarly data artifact.

Serialises a ``ComparisonResult`` as TEI using the parallel segmentation
method. See docs/adr/0006-tei-parallel-segmentation-export.md for why that
method and not double-end-point attachment or location referencing.

The property that makes this an archive rather than a rendering: selecting
every ``<rdg wit="#A">`` and concatenating reproduces Manuscript A, and the
same for B. ``tests/unit/test_tei.py`` asserts it against the same token
streams the reader sees.

Serialised with the standard library. The document is a few megabytes of plain
markup at worst, which does not justify a compiled XML dependency or the
licence review that comes with one.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator

from app.models.diff import (
    BlockStatus,
    ComparisonResult,
    DiffBlock,
    StanzaBoundary,
    Token,
    TokenStatus,
)
from app.models.document import BlockKind, DocumentSummary

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

#: The identifiers used in ``@wit`` throughout the document.
WITNESS_A = "A"
WITNESS_B = "B"

#: How a ``BlockKind`` is realised in TEI.
#:
#: ``ARTIFACT`` maps to ``<fw>`` — forme work — which is TEI's element for
#: running heads and folio numbers, exactly what the PDF parser classifies as
#: an artifact. The mapping is a genuine correspondence rather than a
#: convenient dumping ground.
_ELEMENT_FOR_KIND: dict[BlockKind, str] = {
    BlockKind.PARAGRAPH: "p",
    BlockKind.HEADING: "head",
    BlockKind.VERSE_LINE: "l",
    BlockKind.QUOTE: "quote",
    BlockKind.LIST_ITEM: "item",
    BlockKind.ARTIFACT: "fw",
}

#: Structural relations, as ``<linkGrp type=...>`` in ``<back>``.
_LINK_TYPE_FOR_STATUS: dict[BlockStatus, str] = {
    BlockStatus.MOVED: "moved",
    BlockStatus.SPLIT: "split",
    BlockStatus.MERGED: "merged",
}


def _qname(tag: str) -> str:
    return f"{{{TEI_NS}}}{tag}"


def _sub(parent: ET.Element, tag: str, **attrs: str) -> ET.Element:
    return ET.SubElement(parent, _qname(tag), attrs)


def _xml_id(element: ET.Element, value: str) -> None:
    element.set(f"{{{XML_NS}}}id", value)


def block_xml_id(block: DiffBlock) -> str:
    """Stable identifier a citation or a ``<link>`` can point at."""
    return f"blk-{block.id}"


def _append_text(element: ET.Element, children: list[ET.Element], text: str) -> None:
    """Append character data at the current end of ``element``.

    XML puts text either in a parent's ``text`` or in the ``tail`` of whichever
    child precedes it. Getting this wrong is the classic way to silently lose
    or reorder content, and every token here carries its own trailing
    whitespace, so a dropped tail would fuse two words together.
    """
    if not text:
        return
    if children:
        last = children[-1]
        last.tail = (last.tail or "") + text
    else:
        element.text = (element.text or "") + text


class _Run:
    """A maximal stretch of tokens sharing one apparatus entry.

    ``UNCHANGED`` text is emitted as character data; a stretch of
    ``DELETION``/``INSERTION`` becomes one ``<app>``. Emitting one ``<app>``
    per token would shatter a rewritten sentence into dozens of apparatus
    entries, which is unreadable as an apparatus even though it carries the
    same information.
    """

    __slots__ = ("a_text", "b_text", "unchanged")

    def __init__(self, *, unchanged: bool) -> None:
        self.unchanged = unchanged
        self.a_text = ""
        self.b_text = ""


def _runs(tokens: list[Token]) -> Iterator[_Run]:
    current: _Run | None = None

    for token in tokens:
        unchanged = token.status is TokenStatus.UNCHANGED
        if current is None or current.unchanged != unchanged:
            if current is not None:
                yield current
            current = _Run(unchanged=unchanged)

        if unchanged:
            current.a_text += token.text
            current.b_text += token.text
        elif token.status is TokenStatus.DELETION:
            current.a_text += token.text
        else:
            current.b_text += token.text

    if current is not None:
        yield current


def _append_app(parent: ET.Element, children: list[ET.Element], run: _Run) -> None:
    """Emit one apparatus entry holding the two witnesses' readings.

    An empty ``<rdg>`` is TEI's way of saying a witness omits the passage
    entirely, which is what a pure insertion or deletion is. It must still be
    present: dropping the element would say the witness was not collated here,
    not that it reads nothing.
    """
    app = _sub(parent, "app")
    a_rdg = _sub(app, "rdg", wit=f"#{WITNESS_A}")
    if run.a_text:
        a_rdg.text = run.a_text
    b_rdg = _sub(app, "rdg", wit=f"#{WITNESS_B}")
    if run.b_text:
        b_rdg.text = run.b_text
    children.append(app)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _witness_description(summary: DocumentSummary) -> str:
    return f"{summary.title} ({summary.source_format.value})"


def _build_header(comparison: ComparisonResult) -> ET.Element:
    header = ET.Element(_qname("teiHeader"))

    file_desc = _sub(header, "fileDesc")

    title_stmt = _sub(file_desc, "titleStmt")
    _sub(title_stmt, "title").text = f"Collation of {comparison.a.title} and {comparison.b.title}"

    publication_stmt = _sub(file_desc, "publicationStmt")
    _sub(publication_stmt, "p").text = (
        "Generated by palimpsest. This file records a collation of two "
        "witnesses and is not an edition: no reading is presented as "
        "authoritative, and the witnesses are given in upload order rather "
        "than in any stemmatic relation."
    )

    source_desc = _sub(file_desc, "sourceDesc")
    list_wit = _sub(source_desc, "listWit")
    witness_a = _sub(list_wit, "witness")
    _xml_id(witness_a, WITNESS_A)
    witness_a.text = _witness_description(comparison.a)
    witness_b = _sub(list_wit, "witness")
    _xml_id(witness_b, WITNESS_B)
    witness_b.text = _witness_description(comparison.b)

    encoding_desc = _sub(header, "encodingDesc")
    _sub(
        encoding_desc,
        "variantEncoding",
        method="parallel-segmentation",
        location="internal",
    )

    # Metrics go in prose because TEI has no vocabulary for a similarity score
    # or an edit count, and inventing attributes would produce markup that no
    # consumer of this file can interpret.
    metrics = comparison.metrics
    _sub(encoding_desc, "p").text = (
        f"Collated automatically at {comparison.options.granularity.value.lower()} "
        f"granularity. Similarity {metrics.similarity:.3f}; "
        f"{_plural(metrics.insertions, 'word')} inserted, "
        f"{_plural(metrics.deletions, 'word')} deleted, "
        f"{_plural(metrics.unchanged_tokens, 'word')} unchanged. "
        f"{_plural(metrics.blocks_moved, 'block')} moved, "
        f"{_plural(metrics.blocks_split, 'block')} split, "
        f"{_plural(metrics.blocks_merged, 'block')} merged. "
        "Structural relations between blocks are recorded as linkGrp elements "
        "in the back matter, because the TEI apparatus module describes "
        "variation in reading rather than transposition of passages."
    )

    return header


def _append_body(body: ET.Element, blocks: list[DiffBlock]) -> None:
    """Lay out the collation, gathering verse lines into line groups.

    A bare ``<l>`` is not how TEI presents verse. Lines belong to a ``<lg>``,
    and a consumer that renders or queries poetry expects to find them there.

    A new line group begins wherever either witness begins a stanza, which is
    what ``DiffBlock.stanza_boundary`` records. ADR-0006 had to settle for one
    group per contiguous run of verse, because the payload carried nothing
    finer; ADR-0007 gave it stanza boundaries and the grouping is now exact.

    Where the witnesses disagree about a break, the group is still divided
    there. The disagreement is not discarded — it is the finding — but a TEI
    document has one body, so it takes the division either witness attests
    rather than inventing a third structure that neither has.
    """
    group: ET.Element | None = None

    for block in blocks:
        if block.kind is not BlockKind.VERSE_LINE:
            group = None
            _append_block(body, block)
            continue

        if group is None or block.stanza_boundary is not StanzaBoundary.NONE:
            group = _sub(body, "lg")

        _append_block(group, block)


def _append_block(parent: ET.Element, block: DiffBlock) -> ET.Element:
    element = _sub(parent, _ELEMENT_FOR_KIND.get(block.kind, "p"))
    _xml_id(element, block_xml_id(block))

    children: list[ET.Element] = []
    for run in _runs(block.tokens):
        if run.unchanged:
            _append_text(element, children, run.a_text)
        else:
            _append_app(element, children, run)

    return element


def _append_structural_links(back: ET.Element, blocks: list[DiffBlock]) -> None:
    """Record moves, splits and merges as typed links between block ids.

    Grouped by relation so a consumer can select all transpositions at once,
    and so a split of one paragraph into three is a single link naming three
    targets rather than three unrelated assertions.
    """
    groups: dict[str, dict[str, list[str]]] = {}

    for block in blocks:
        link_type = _LINK_TYPE_FOR_STATUS.get(block.status)
        if link_type is None:
            continue
        # A group_id ties the members of one split or merge together; a moved
        # block stands alone and is keyed by its own id.
        key = block.group_id or block.id
        groups.setdefault(link_type, {}).setdefault(key, []).append(block_xml_id(block))

    for link_type in ("moved", "split", "merged"):
        members = groups.get(link_type)
        if not members:
            continue
        link_grp = _sub(back, "linkGrp", type=link_type)
        for targets in members.values():
            _sub(link_grp, "link", target=" ".join(f"#{t}" for t in targets))


#: Elements whose contents are readings rather than structure. Nothing inside
#: one of these may be reindented.
_CONTENT_ELEMENTS = frozenset(_ELEMENT_FOR_KIND.values())


def _indent(element: ET.Element, level: int = 0) -> None:
    """Indent the structural skeleton, never the content.

    Neither ``minidom.toprettyxml`` nor ``ET.indent`` is safe here. Both will
    happily insert a newline and indentation as the ``text`` of an element
    whose first child is an ``<app>`` — which is every block that opens with a
    changed word — and as the ``tail`` of a trailing ``<app>``. That whitespace
    lands *inside* a reading, so the exported witness no longer matches the
    witness, and the reconstruction property this format exists for is
    silently lost.

    So descent stops at any element that carries a reading. Its own tail is
    still set by its parent, which is outside it and therefore harmless.
    """
    if element.tag.rpartition("}")[2] in _CONTENT_ELEMENTS:
        return

    if not len(element):
        return

    pad = "\n" + "  " * level
    child_pad = "\n" + "  " * (level + 1)

    if not (element.text or "").strip():
        element.text = child_pad

    last = len(element) - 1
    for position, child in enumerate(element):
        _indent(child, level + 1)
        if not (child.tail or "").strip():
            child.tail = pad if position == last else child_pad


def build_tei(comparison: ComparisonResult) -> str:
    """Serialise a comparison as a TEI P5 document.

    Raises ``ValueError`` if the comparison is windowed, because a partial
    collation exported as a whole one would be a quietly wrong scholarly
    artifact — the worst kind.
    """
    if comparison.truncated:
        raise ValueError(
            "Refusing to export a windowed comparison: the export would look "
            "complete while omitting blocks."
        )

    root = ET.Element(_qname("TEI"))
    root.append(_build_header(comparison))

    text = _sub(root, "text")
    body = _sub(text, "body")
    _append_body(body, comparison.blocks)

    back = _sub(text, "back")
    _append_structural_links(back, comparison.blocks)
    if len(back) == 0:
        text.remove(back)

    _indent(root)

    ET.register_namespace("", TEI_NS)
    serialised = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{serialised}\n'
