# Module boundaries

The backend boundary is deliberately narrow:

```{mermaid}
flowchart LR
  Upload[Uploaded bytes and metadata] --> Ingestion[ingestion]
  Ingestion --> Document[canonical Document]
  Document --> Diffing[diffing]
  Diffing --> DiffResult[diff-domain blocks and metrics]
  DiffResult --> Formatting[formatting]
  Formatting --> Payload[ComparisonResult / BlockPage]
  Formatting --> TEI[TEI P5]
```

## ingestion

`ingestion` is the only layer that knows about source formats. It probes bytes and upload metadata, selects a parser, normalizes text, creates blocks, records warnings, and returns a canonical `Document`.

## diffing

`diffing` receives two `Document` values and `DiffOptions`. It tokenizes, aligns blocks, computes word or character diffs, classifies `MOVED`, `SPLIT`, and `MERGED`, and produces metrics. It does not know whether a witness came from `.txt`, `.docx`, or `.pdf`.

## formatting

`formatting` owns the wire shape. It serializes diff-domain results as `ComparisonResult` and `BlockPage`, prepares token streams for synoptic and unified rendering, and exports TEI P5.

This separation is what makes parsers replaceable and keeps the renderer from becoming a second diff engine.
