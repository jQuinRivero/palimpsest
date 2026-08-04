# palimpsest — technical specification

> A palimpsest is a manuscript page scraped clean and written over, where the earlier text still shows faintly through. This project is named for that: the prior reading is never destroyed, only overlaid.

This directory is the normative specification for `palimpsest`, an open-source tool for reading the difference between two versions of a literary text.

**Status:** Draft · **License:** Apache-2.0 · **Audience:** contributors implementing the system

---

## Reading order

Start at `00` and read forward. Documents `04` and `05` are load-bearing — everything downstream depends on the contracts they define.

| # | Document | What it settles |
|---|---|---|
| 00 | [Overview](./00-overview.md) | Vision, the researcher we build for, scope, non-goals, glossary |
| 01 | [Architecture](./01-architecture.md) | System context, module map, request lifecycle, deployment |
| 02 | [Ingestion and parsers](./02-ingestion-and-parsers.md) | `BaseDocumentParser`, the registry, and the OCR seam |
| 03 | [Normalization](./03-normalization.md) | The canonical `Document`, dehyphenation, reflow, segmentation |
| 04 | [Diff engine](./04-diff-engine.md) | Word-level diffing, block alignment, move/split/merge detection |
| 05 | [Data schema](./05-data-schema.md) | The JSON payload contract and its TypeScript mirror |
| 06 | [API reference](./06-api-reference.md) | REST surface, status codes, error taxonomy, limits |
| 07 | [Session storage](./07-session-storage.md) | SQLite schema, TTL sweeper, shareable comparison URLs |
| 08 | [Frontend architecture](./08-frontend-architecture.md) | App Router structure, data fetching, URL as state |
| 09 | [Design system](./09-design-system.md) | Typography-first tokens and the diff visual language |
| 10 | [Components](./10-components.md) | `ManuscriptUploader`, `DiffViewer`, `SyncScrollContainer`, `DiffSummaryBar` |
| 11 | [Performance and scale](./11-performance-and-scale.md) | Budgets for 100k+ word manuscripts, virtualization, backpressure |
| 12 | [Edge cases](./12-edge-cases.md) | PDF noise, hyphens, ligatures, encodings, RTL, footnotes |
| 13 | [Testing strategy](./13-testing-strategy.md) | Unit, golden-corpus, contract, and end-to-end testing |
| 14 | [Roadmap](./14-roadmap.md) | OCR activation, multi-witness collation, annotation, export |
| — | [Architecture decision records](./adr/README.md) | Why the contested calls went the way they did |

---

## The shape of the system in one paragraph

A researcher uploads two witnesses. Each is handed to a parser resolved from its media type and magic bytes; whatever the format, the parser returns the same canonical `Document` of `Block`s. The diff engine then runs in two stages: it first *aligns* blocks between the two witnesses using a similarity matrix — which is what lets it recognise that a paragraph was moved, split, or merged rather than simply deleted and rewritten — and then runs a word-level diff *within* each aligned pair. The result is serialised to a structured payload of blocks and typed tokens, cached in SQLite under an unguessable id with a TTL, and rendered by a typography-first React client in either synoptic or unified view.

---

## Conventions used throughout

**Terminology is fixed.** These words are used precisely and consistently; synonyms are avoided because they cause drift in code as much as in prose.

| Term | Meaning |
|---|---|
| **witness** | One uploaded version of the text (Manuscript A or Manuscript B) |
| **block** | The atomic unit of *alignment* — a paragraph, heading, or verse line |
| **token** | The atomic unit of *diffing* — a word plus its trailing whitespace |
| **alignment** | Stage 1: establishing block-to-block correspondence between witnesses |
| **collation** | The whole A-versus-B operation, alignment and diffing together |
| **synoptic** | The side-by-side view |
| **unified** | The single-column view |

Witnesses are always **Manuscript A** and **Manuscript B**, never "left" and "right" — the panes swap under right-to-left scripts and collapse entirely in unified view.

**Other conventions.** Identifiers in these documents are normative: type names, field names, enum values, endpoint paths, and design token names are written exactly as they must appear in code. JSON is `snake_case` on the wire, matching the Python models without aliasing. Every document opens with a purpose line and links to its neighbours. Pinned dependency versions are the versions verified when the specification was written; treat them as floors rather than locks.

---

## Licensing constraint

The project is Apache-2.0, and that materially constrains dependency choice. Copyleft libraries are disqualifying regardless of technical merit — this is why `pdfplumber` is specified over the more capable `PyMuPDF` (AGPL-3.0), and `rapidfuzz` over `python-Levenshtein` (GPL-2.0). Any proposal to add a dependency must state its license. See [ADR-0002](./adr/0002-pdfplumber-over-pymupdf.md).
