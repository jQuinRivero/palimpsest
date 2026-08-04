This document defines the purpose, scope, vocabulary, and product boundaries for `palimpsest`.

**Status:** Draft

**Related:** [Architecture](./01-architecture.md) · [Ingestion and parsers](./02-ingestion-and-parsers.md) · [Normalization](./03-normalization.md) · [Diff engine](./04-diff-engine.md) · [Design system](./09-design-system.md) · [Roadmap](./14-roadmap.md)

## The problem

Existing diff tools are built for source code. They are monospace, line-oriented, and optimized for dense red/green blocks that answer whether a patch can be reviewed, not whether a prose change can be read. They also treat a reflowed paragraph as a total rewrite because the unit of comparison is usually a physical line.

Researchers comparing manuscript drafts, translations, or editions need something else. They need to read the difference at length, with typography that preserves the experience of sustained prose. They also care about structural evolution: a paragraph moved to a new chapter, a long passage split in two, or two passages merged into one. A line-based diff cannot express those relationships without turning meaningful revision into noise.

`palimpsest` exists to make those relationships legible. It aligns blocks first, diffs tokens second, and renders the result as a manuscript page rather than a code review.

## Who this is for

The primary user is a researcher in literary studies, textual criticism, or translation studies. This user is technically literate enough to upload witnesses, interpret metrics, and cite a comparison URL, but is not expected to be a developer or to understand source-control tooling.

Secondary users include editors comparing prose drafts and digital-humanities projects that need a citable comparison URL for two witnesses.

## What v1 does

In v1, a researcher uploads two witnesses: Manuscript A and Manuscript B. Each witness may be supplied as `.txt`, `.md`, `.docx`, or `.pdf`. The system returns a block-aligned, word-level collation that can be read in either synoptic or unified view.

The result includes:

- aligned `Block` records for Manuscript A and Manuscript B;
- token-level `UNCHANGED`, `INSERTION`, and `DELETION` markup;
- block statuses including `UNCHANGED`, `MODIFIED`, `INSERTED`, `DELETED`, `MOVED`, `SPLIT`, and `MERGED`;
- summary metrics for similarity, edit count, insertions, deletions, churn, moved blocks, split blocks, and merged blocks;
- a shareable, expiring comparison URL backed by an unguessable `comparison_id` and TTL-based session storage.

## Explicit non-goals for v1

| Non-goal | Reason |
|---|---|
| No user accounts, authentication, or persistent libraries | Sessions use an unguessable id plus TTL; v1 is a read-only comparison tool, not a personal archive. |
| No editing or merging | `palimpsest` is read-only; it explains differences but is not a merge tool. |
| No more than two witnesses at a time | Multi-witness collation is roadmap scope, and v1 keeps the `ComparisonResult` contract focused on Manuscript A versus Manuscript B. |
| No OCR of scanned PDFs in v1 | The seam is designed in through `AsyncOCRParser` and OCR-reserved fields, but no OCR engine ships in v1; see [Ingestion and parsers](./02-ingestion-and-parsers.md). |
| No real-time collaboration | Shareable comparison URLs support asynchronous citation and review without introducing shared editing state. |
| No semantic or meaning-level diffing | Differences are lexical; the system compares blocks and tokens, not interpretation or meaning. |

## Design principles

1. **Reading comes first.** The interface is a manuscript page, not a code review, so layout, measure, leading, and change marks must support sustained reading.
2. **Do not reinvent the wheel.** Proven libraries do the underlying diffing and extraction work; the project value is alignment, normalization, and presentation for literary witnesses.
3. **Every parser is replaceable.** Parsers may know about `.txt`, `.md`, `.docx`, `.pdf`, or future `OCR`, but none may leak format-specific concerns into the diff pipeline.
4. **The server computes, the client renders.** The backend returns a finished `ComparisonResult`; the frontend renders typed blocks and tokens without running the diff engine.
5. **Be honest about uncertainty.** Ingestion warnings and low-confidence alignments must be surfaced rather than silently guessed away.

## Glossary

| Term | Definition |
|---|---|
| **witness** | One uploaded version of the text, either Manuscript A or Manuscript B; a witness is the object being compared, not merely its source bytes. |
| **block** | The atomic unit of alignment, usually a paragraph, heading, verse line, quote, or list item represented as a `Block`. |
| **token** | The atomic unit of diffing; in `WORD` granularity, a token is a word plus its trailing whitespace and is represented as a `Token`. |
| **alignment** | Stage 1 of the diffing process, where the system establishes block-to-block correspondence between Manuscript A and Manuscript B before token diffing. |
| **collation** | In textual criticism, collation is the systematic comparison of witnesses to record variation; this specification uses the term loosely for the whole A-versus-B operation, including alignment and token diffing. |
| **synoptic** | The side-by-side view mode, represented by `SYNOPTIC`, where corresponding material from Manuscript A and Manuscript B is read in parallel. |
| **unified** | The single-column view mode, represented by `UNIFIED`, where the comparison is rendered as one continuous reading stream. |
| **granularity** | The configured token scale for diffing, represented by `Granularity`; v1 defaults to `WORD`, with `CHARACTER` available for finer inspection. |
| **churn** | A normalized metric describing how much of the compared text changed, based on insertions and deletions relative to the token population. |
| **similarity** | A score from `0.0` to `1.0` that describes how closely two blocks or witnesses match after normalization. |
| **move detection** | The detection of aligned blocks whose order is non-monotonic, producing `MOVED` status and a `move_distance`. |
| **normalization** | The ingestion step that converts parser output into canonical text, block boundaries, offsets, and metadata before diffing. |
| **dehyphenation** | A normalization operation that repairs line-break hyphen artifacts when the source format has split a word across visual lines. |
| **artifact block** | A `Block` with kind `ARTIFACT`, such as a running head, folio number, or footer, extracted for transparency but excluded from diffing by default. |

## The name

A palimpsest is a manuscript scraped and overwritten while the earlier text still shows through. The name commits the product to that visual language: the prior reading is not destroyed or shouted down in red, but remains visible beneath and beside the later reading. The design system in [Design system](./09-design-system.md) must make revision feel layered, legible, and typographic rather than punitive.
