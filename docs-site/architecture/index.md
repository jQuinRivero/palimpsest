# Architecture overview

palimpsest is a two-part web application:

- a FastAPI backend that parses witnesses, computes the collation, stores expiring sessions, and exports TEI;
- a Next.js / React frontend that uploads witnesses and renders a finished comparison payload.

The important architectural choice is that the browser renders truth produced by the server. It does not parse `.docx` or `.pdf`, align blocks, compute metrics, or infer structural relationships.

```{mermaid}
flowchart LR
  A[Researcher uploads Manuscript A and B] --> B[FastAPI]
  B --> C[ingestion]
  C --> D[canonical Document models]
  D --> E[diffing]
  E --> F[formatting]
  F --> G[ComparisonResult JSON]
  G --> H[Next.js reader]
  F --> I[TEI P5 export]
  B <--> J[(SQLite TTL session store)]
```

Normative detail: [architecture](https://github.com/jQuinRivero/palimpsest/blob/main/docs/01-architecture.md).
