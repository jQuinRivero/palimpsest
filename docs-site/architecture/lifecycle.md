# Request lifecycle

The lifecycle is upload, parse, persist, compare, persist, render.

```{mermaid}
sequenceDiagram
  participant Browser
  participant API as FastAPI /api/v1
  participant Ingestion as ingestion
  participant Store as SQLite SessionStore
  participant Diffing as diffing
  participant Formatting as formatting

  Browser->>API: POST /documents (Manuscript A)
  API->>Ingestion: SourceProbe + DocumentSource
  Ingestion-->>API: Document
  API->>Store: store Document
  API-->>Browser: 201 DocumentSummary

  Browser->>API: POST /documents (Manuscript B)
  API->>Ingestion: SourceProbe + DocumentSource
  Ingestion-->>API: Document
  API->>Store: store Document
  API-->>Browser: 201 DocumentSummary

  Browser->>API: POST /comparisons
  API->>Store: load Documents
  API->>Diffing: Document A + Document B + DiffOptions
  Diffing-->>Formatting: diff-domain blocks and metrics
  Formatting-->>API: ComparisonResult
  API->>Store: store comparison until expires_at
  API-->>Browser: 201 ComparisonResult or 202 ComparisonAccepted
```

For large work, the API may return `202 ComparisonAccepted`; the client polls the comparison URL until the finished `ComparisonResult` is available. Finished comparisons can be fetched by ID, paged by block window, deleted, or exported as TEI.
