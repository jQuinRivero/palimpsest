"""Round-trip every registered format through the live API.

This is the proof of the claim in docs/02-ingestion-and-parsers.md that the
diff pipeline never learns about file formats: a `.docx` and a `.txt` carrying
the same words must produce the same collation.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"

PROSE_A = "It was the best of times.\n\nIt was the age of wisdom."
PROSE_B = "It was the brightest of times.\n\nIt was the age of wisdom."


def build_docx(paragraphs: list[str]) -> bytes:
    from docx import Document

    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_pdf(paragraphs: list[str]) -> bytes:
    sys.path.insert(0, "tests")
    from pdf_builder import build_pdf as make
    from pdf_builder import prose_page

    return make([prose_page(paragraphs)])


def upload(data: bytes, filename: str, media_type: str, title: str) -> dict:
    boundary = "----palimpsest-probe"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    body += f"Content-Type: {media_type}\r\n\r\n".encode()
    body += data + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="title"\r\n\r\n'
    body += title.encode() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    request = urllib.request.Request(
        f"{BASE}/api/v1/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def compare(a_id: str, b_id: str) -> dict:
    request = urllib.request.Request(
        f"{BASE}/api/v1/comparisons",
        data=json.dumps({"a_document_id": a_id, "b_document_id": b_id}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


FORMATS = [
    (
        "txt",
        lambda text: text.encode("utf-8"),
        "witness.txt",
        "text/plain",
    ),
    (
        "md",
        lambda text: f"# Chapter\n\n{text}".encode(),
        "witness.md",
        "text/markdown",
    ),
    (
        "docx",
        lambda text: build_docx(text.split("\n\n")),
        "witness.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    (
        "pdf",
        lambda text: build_pdf(text.split("\n\n")),
        "witness.pdf",
        "application/pdf",
    ),
]

failures = 0
uploaded: dict[str, tuple[str, str]] = {}

print(f"{'format':8} {'parser':12} {'blocks':>6} {'words':>6}  warnings")
print("-" * 68)

for label, build, filename, media_type in FORMATS:
    try:
        a = upload(build(PROSE_A), filename, media_type, f"A ({label})")
        b = upload(build(PROSE_B), filename, media_type, f"B ({label})")
    except Exception as exc:
        print(f"{label:8} UPLOAD FAILED: {exc}")
        failures += 1
        continue

    uploaded[label] = (a["id"], b["id"])
    warnings = ",".join(w["code"] for w in a["warnings"]) or "-"
    print(
        f"{label:8} {a['metadata']['parser_name']:12} "
        f"{a['metadata']['block_count']:>6} {a['metadata']['word_count']:>6}  {warnings}"
    )

print()
print("collations:")
baseline = None
for label, (a_id, b_id) in uploaded.items():
    result = compare(a_id, b_id)
    metrics = result["metrics"]
    signature = (metrics["insertions"], metrics["deletions"])
    print(
        f"  {label:6} similarity={metrics['similarity']:.4f} "
        f"+{metrics['insertions']}/-{metrics['deletions']} "
        f"blocks={result['total_blocks']}"
    )
    # Markdown carries an extra heading block, so compare only the edit shape.
    if label in ("txt", "docx", "pdf"):
        if baseline is None:
            baseline = signature
        elif signature != baseline:
            print(f"    MISMATCH: {label} edit shape {signature} != txt {baseline}")
            failures += 1

print()
if failures:
    print(f"{failures} FAILURE(S)")
else:
    print("Every format ingests, and txt/docx/pdf produce an identical edit shape.")

raise SystemExit(1 if failures else 0)
