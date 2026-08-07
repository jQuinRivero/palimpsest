# Supported formats

The server chooses a parser from filename, media type, magic bytes, and size. Extension alone is not authoritative.

| Format | Parser | What it preserves | Important caveat |
|---|---|---|---|
| `.txt` | `PlainTextParser` | Text content losslessly after decoding and normalization | It does not infer headings from short lines. |
| `.md`, `.markdown` | `MarkdownParser` | Structure such as headings, block quotes, and list items | Inline formatting is stripped so Markdown markup is not treated as a textual variant. |
| `.docx` | `DocxParser` | Main document body and heading/list/quote styles | Tracked changes, comments, footnotes, and endnotes are warned about rather than silently treated as compared body text. |
| `.pdf` | `PdfPlumberParser` | Page provenance and layout-aware positional reconstruction | Running heads and folio numbers may become `ARTIFACT` blocks; paragraphs are rebuilt from vertical gaps. |
| `.pdf` | `PyPdfParser` | Page-local extracted text for simpler PDFs | It is faster and lower fidelity than `pdfplumber`. |

Scanned PDFs are refused with `OCR_REQUIRED` when sampled pages have effectively no extractable text. That is deliberate: returning an empty document would say the witness has no text, which is false.

Normative detail: [ingestion and parsers](https://github.com/jQuinRivero/palimpsest/blob/main/docs/02-ingestion-and-parsers.md).
