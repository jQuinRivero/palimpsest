# Contracts and extension seams

## Parser contract

Every parser implements `BaseDocumentParser`: it advertises capabilities, answers whether it can parse a cheap `SourceProbe`, and returns a canonical `Document` from `DocumentSource`.

OCR does not ship in v1, but the seam is present. `AsyncOCRParser` returns the same `Document` model through an async path. OCR-specific fields already exist as nullable contract members: `Block.confidence`, `Block.bbox`, `DocumentMetadata.ocr_confidence`, parser capability flags, and `SourceFormat.OCR`.

```{mermaid}
classDiagram
  class BaseDocumentParser {
    +capabilities() ParserCapabilities
    +can_parse(SourceProbe) bool
    +parse(DocumentSource) Document
  }
  class AsyncDocumentParser {
    +parse_async(DocumentSource) Document
  }
  class AsyncOCRParser
  BaseDocumentParser <|-- AsyncDocumentParser
  AsyncDocumentParser <|-- AsyncOCRParser
  BaseDocumentParser <|-- PlainTextParser
  BaseDocumentParser <|-- MarkdownParser
  BaseDocumentParser <|-- DocxParser
  BaseDocumentParser <|-- PdfPlumberParser
  BaseDocumentParser <|-- PyPdfParser
```

## Payload contract

The payload is the API. `ComparisonResult`, `DiffBlock`, token streams, metrics, options, and pagination metadata are produced by the backend and rendered by the frontend. JSON field names stay `snake_case`, matching the Python models.

The frontend's TypeScript API types are generated from the backend OpenAPI schema and committed. That makes schema drift reviewable: generated types change in the same repository diff as the backend contract.

## Why collation runs server-side

Server-side collation avoids duplicating parsing, alignment, move/split/merge detection, tokenization, and metrics across Python and JavaScript. It also lets the server enforce budgets and return `202` or `DIFF_BUDGET_EXCEEDED` instead of hanging a researcher's browser tab.

Decision record: [ADR-0004](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0004-server-side-diff-computation.md).
