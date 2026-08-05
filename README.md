# palimpsest

![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)
![Status: v1 complete](https://img.shields.io/badge/status-v1%20complete-green)

An open-source literary-criticism web app for reading how one witness of a text changes into another.

## What it is

`palimpsest` is an open-source tool for reading the difference between two versions of a literary text. It supports synoptic or unified reading, word-level tokens, and structural evolution such as moved, split, and merged passages instead of treating a reflowed block as a rewrite.

## The name

A palimpsest is a manuscript scraped clean and written over, where the earlier text still shows faintly through. That is the product metaphor: the prior reading shows through rather than being struck out in red, and the visual language is built around layered manuscript colour and typography.

## Why not just use `diff`

Code-oriented diff tools are line-oriented, monospace, dense, and red/green by default. They are excellent for source code, but poor for prose: they overstate paragraph reflow, miss moved passages, and make literary reading feel like patch review.

## Features

- Supported witness formats: `.txt`, `.md`, `.docx`, and `.pdf`.
- Synoptic and unified views for close reading.
- Word-level tokens with insertion, deletion, and unchanged status.
- Block alignment with moved, split, and merged passage detection.
- Verse read as verse: a poem is compared line by line, so a transposed line reads as a move rather than a rewrite.
- Change metrics for similarity, churn, insertions, deletions, and structural changes.
- TEI P5 export using parallel segmentation, so a collation can leave the tool.
- Shareable expiring comparison URLs backed by a TTL session cache.

## Status

**v1 is complete.** Every capability the specification describes for v1 is built, tested, and running: upload two witnesses in any supported format, get a structurally aware word-level diff, and read it side by side or unified in the browser.

Working today:

- **Ingestion**: `BaseDocumentParser` interface, parser registry with three-signal format detection, and parsers for `.txt`, `.md`, `.docx`, `.pdf` — the last with running-head and folio-number detection, and honest `OCR_REQUIRED` refusal of scanned PDFs
- **Normalization**: Unicode NFC, ligature folding, soft line-break reflow with verse exemption, and a lexicon-backed dehyphenation policy that distinguishes hard hyphens from typesetter hyphens
- **Verse**: poetry is segmented into one block per line, so alignment happens at the line rather than the stanza — a revised word marks one line, and a transposed line reports as `MOVED` with no wording change. Stanza breaks survive segmentation, so re-dividing a poem is reported rather than passing as identical. Detection is biased toward prose and always announced, because shredding a paragraph is worse than missing a poem
- **Alignment**: exact-match anchoring, gap-confined fuzzy search, deterministic greedy assignment, LIS-based move detection, and split/merge detection via the concatenation test — so re-paragraphing a chapter reports a `SPLIT` with **zero** word edits rather than a rewrite
- **Diff engine**: word-level diffing via `diff-match-patch` line-mode remapping, all three token streams, and full metrics
- **API and storage**: REST API with an RFC 9457 error taxonomy, a `202` accepted-and-poll path for large manuscripts, windowed block fetching, rate limiting, and a SQLite session store with a scheduled TTL sweeper
- **Reading**: synoptic and unified views in the manuscript design system, virtualized so a 100k-word witness scrolls without jank, with keyboard change navigation, citable `?block=` deep links, and a print stylesheet that survives greyscale
- **Export**: TEI P5 using the parallel segmentation method, with moves, splits and merges recorded as `<linkGrp>` in the back matter and verse gathered into `<lg>` — both witnesses reconstruct from the file word for word

Not built, and deliberately so: OCR (the seam exists, no engine ships), multi-witness collation, annotation, and independently scrolling panes. See the [roadmap](docs/14-roadmap.md).

The [specification](docs/README.md) remains normative. Where the code and the specification disagree, that is a defect in one of them.

## Supported formats

| Format | Parser | Preserves headings | Notes |
|---|---|---|---|
| `.txt` | `plaintext` | — | BOM and encoding detection; lossless |
| `.md`, `.markdown` | `markdown` | yes | Structure only — inline formatting is stripped, because a prose diff should not diff asterisks |
| `.docx` | `docx` | yes | Warns on tracked changes, comments and footnotes rather than silently dropping them |
| `.pdf` | `pdfplumber` | — | Positional analysis: running heads become `ARTIFACT` blocks, paragraphs are rebuilt from vertical gaps |
| `.pdf` | `pypdf` | — | Faster, lower-fidelity fallback for simple documents |

Scanned PDFs are refused with `OCR_REQUIRED` rather than returning an empty document. The OCR seam is designed in — see [ingestion](docs/02-ingestion-and-parsers.md) — but no OCR engine ships.

## Running it

Requires Python 3.12+ (provisioned automatically by [uv](https://docs.astral.sh/uv/)) and Node 20+.

```bash
# API on http://127.0.0.1:8000
cd backend && uv sync --all-groups && uv run uvicorn app.main:app --reload

# Web on http://localhost:3000
cd frontend && npm install && npm run dev
```

Tests:

```bash
cd backend  && uv run pytest            # unit, property, golden corpus, API
cd frontend && npm run typecheck && npm run lint && npm run test:e2e
```

The client's TypeScript types are generated from the API's OpenAPI schema and committed, so they cannot drift from the backend:

```bash
cd frontend && npm run gen:types        # regenerate
cd frontend && npm run check:types-drift  # CI fails if stale
```

## Documentation

| # | Document | Description |
|---|---|---|
| — | [Documentation index](docs/README.md) | Normative specification index, reading order, terminology, and licensing constraint. |
| 00 | [Overview](docs/00-overview.md) | Vision, researcher profile, scope, non-goals, and glossary. |
| 01 | [Architecture](docs/01-architecture.md) | System context, module map, request lifecycle, and deployment shape. |
| 02 | [Ingestion and parsers](docs/02-ingestion-and-parsers.md) | Parser interfaces, registry behaviour, supported formats, and the OCR seam. |
| 03 | [Normalization](docs/03-normalization.md) | Canonical `Document` production, dehyphenation, reflow, and segmentation. |
| 04 | [Diff engine](docs/04-diff-engine.md) | Two-stage block alignment and word-level token diffing. |
| 05 | [Data schema](docs/05-data-schema.md) | JSON payload contract and TypeScript mirror. |
| 06 | [API reference](docs/06-api-reference.md) | REST endpoints, status codes, errors, and limits. |
| 07 | [Session storage](docs/07-session-storage.md) | SQLite TTL cache, sweeper, and shareable comparison URLs. |
| 08 | [Frontend architecture](docs/08-frontend-architecture.md) | Next.js App Router structure, data fetching, and URL state. |
| 09 | [Design system](docs/09-design-system.md) | Typography-first Tailwind v4 tokens and diff visual language. |
| 10 | [Components](docs/10-components.md) | Core React components for upload, viewing, scrolling, and summaries. |
| 11 | [Performance and scale](docs/11-performance-and-scale.md) | Budgets, virtualization, payload windowing, and backpressure. |
| 12 | [Edge cases](docs/12-edge-cases.md) | PDF noise, hyphens, ligatures, encodings, RTL, and footnotes. |
| 13 | [Testing strategy](docs/13-testing-strategy.md) | Unit, golden-corpus, contract, and end-to-end testing. |
| 14 | [Roadmap](docs/14-roadmap.md) | OCR activation, multi-witness collation, annotation, and export. |
| — | [Architecture decision records](docs/adr/README.md) | Accepted decisions for contested architectural and dependency choices. |
| ADR-0001 | [Community diff-match-patch fork](docs/adr/0001-diff-match-patch-fork.md) | Why the Python `diff-match-patch` fork is used for word-level diffing. |
| ADR-0002 | [pdfplumber over PyMuPDF](docs/adr/0002-pdfplumber-over-pymupdf.md) | Why PDF extraction chooses permissive licensing over the strongest AGPL extractor. |
| ADR-0003 | [SQLite session store](docs/adr/0003-sqlite-session-store.md) | Why expiring comparison sessions use SQLite with TTL. |
| ADR-0004 | [Server-side diff computation](docs/adr/0004-server-side-diff-computation.md) | Why collation runs on the backend and returns a structured payload. |
| ADR-0005 | [Tailwind v4 CSS-first tokens](docs/adr/0005-tailwind-v4-css-first-tokens.md) | Why design tokens live in CSS `@theme` instead of `tailwind.config.js`. |

## Architecture at a glance

```text
Manuscript A + Manuscript B
  -> ingestion parsers produce canonical Documents
  -> rapidfuzz aligns blocks, diff-match-patch diffs tokens
  -> FastAPI returns a structured payload rendered by Next.js
```

Stack: Python 3.12+, FastAPI, SQLite with TTL, Next.js 16, React 19, and Tailwind CSS 4.3.3.

## Contributing

Start with the specification in [`docs/README.md`](docs/README.md). Two standing rules apply: any new dependency must declare its license and copyleft is disqualifying under Apache-2.0; architectural changes go through an ADR.

## License

`palimpsest` is licensed under Apache-2.0. That license constrains dependency choice; see [ADR-0002](docs/adr/0002-pdfplumber-over-pymupdf.md) for the precedent.
