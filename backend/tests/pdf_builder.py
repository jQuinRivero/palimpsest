"""Build small, valid PDFs in memory for tests.

Writing raw PDF is unpleasant but it is the right trade here: the alternative
is adding a generation library (reportlab and friends) as a test dependency,
and every one of those carries a licence that would need auditing against the
Apache-2.0 constraint in ADR-0002 for something used only by the test suite.

The output is deliberately plain — a text-only page with positioned lines — but
it is genuinely valid and both `pdfplumber` and `pypdf` read it.
"""

from __future__ import annotations

#: Points from the top of the page for the first line, and leading thereafter.
TOP_MARGIN = 60
LEADING = 18
PAGE_WIDTH = 612
PAGE_HEIGHT = 792


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: list[tuple[str, float, float]], size: int = 11) -> bytes:
    """Build a page content stream from (text, x, y-from-top) triples."""
    parts = ["BT", f"/F1 {size} Tf"]
    for text, x, top in lines:
        y = PAGE_HEIGHT - top
        parts.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
        parts.append(f"({_escape(text)}) Tj")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", errors="replace")


def build_pdf(pages: list[list[tuple[str, float, float]]]) -> bytes:
    """Assemble a PDF from pages of positioned lines.

    Each page is a list of ``(text, x, top)`` where ``top`` is measured from
    the top of the page, matching how `pdfplumber` reports position.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_ids: list[int] = []
    content_ids: list[int] = []
    for lines in pages:
        stream = _content_stream(lines)
        content_ids.append(
            add(
                b"<< /Length "
                + str(len(stream)).encode()
                + b" >>\nstream\n"
                + stream
                + b"\nendstream"
            )
        )
        page_ids.append(0)  # placeholder, filled below

    pages_id = len(objects) + len(pages) + 1

    for index, content_id in enumerate(content_ids):
        page_ids[index] = add(
            b"<< /Type /Page /Parent " + str(pages_id).encode() + b" 0 R"
            b" /MediaBox [0 0 " + str(PAGE_WIDTH).encode() + b" " + str(PAGE_HEIGHT).encode() + b"]"
            b" /Resources << /Font << /F1 " + str(font_id).encode() + b" 0 R >> >>"
            b" /Contents " + str(content_id).encode() + b" 0 R >>"
        )

    kids = b" ".join(str(pid).encode() + b" 0 R" for pid in page_ids)
    actual_pages_id = add(
        b"<< /Type /Pages /Count " + str(len(page_ids)).encode() + b" /Kids [" + kids + b"] >>"
    )
    catalog_id = add(b"<< /Type /Catalog /Pages " + str(actual_pages_id).encode() + b" 0 R >>")

    # Fix up the parent references now that the real Pages id is known.
    for page_id in page_ids:
        objects[page_id - 1] = objects[page_id - 1].replace(
            b"/Parent " + str(pages_id).encode() + b" 0 R",
            b"/Parent " + str(actual_pages_id).encode() + b" 0 R",
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"

    xref_offset = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()

    out += (
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode()
        + b" /Root "
        + str(catalog_id).encode()
        + b" 0 R >>\n"
        b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
    )
    return bytes(out)


def prose_page(
    paragraphs: list[str], *, start_top: float = TOP_MARGIN
) -> list[tuple[str, float, float]]:
    """Lay paragraphs out as lines with a larger gap between paragraphs."""
    lines: list[tuple[str, float, float]] = []
    top = start_top
    for index, paragraph in enumerate(paragraphs):
        if index:
            top += LEADING  # paragraph gap: twice the line leading
        for line in paragraph.split("\n"):
            lines.append((line, 72, top))
            top += LEADING
    return lines


def build_scanned_pdf(page_count: int = 2) -> bytes:
    """A PDF with pages but no text layer, as a scan produces."""
    return build_pdf([[] for _ in range(page_count)])
