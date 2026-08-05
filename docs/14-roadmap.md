This document names plausible future directions for palimpsest without turning them into commitments.

**Status:** Draft

**Related:** [Overview](./00-overview.md) · [Architecture](./01-architecture.md) · [Ingestion and parsers](./02-ingestion-and-parsers.md) · [Diff engine](./04-diff-engine.md) · [Data schema](./05-data-schema.md) · [Session storage](./07-session-storage.md) · [Components](./10-components.md) · [ADR index](./adr/README.md)

## Framing

This roadmap is organized by dependency and value, not by dates, estimates, or sprints. It is a list of seams the v1 design deliberately leaves open. Anything here may be dropped if it stops serving the product goal: helping researchers compare witnesses of literary text.

A roadmap item is not accepted merely because it is listed here. Changes that alter contracts, storage, dependency policy, or user-visible semantics need an architecture decision record through [ADR index](./adr/README.md).

## Near-term themes

### OCR activation

**Motivation.** Many scholarly PDFs are scans. v1 handles them honestly with `OCR_REQUIRED`, but it does not extract their text. Activating OCR turns image-only witnesses into diffable `Document` values instead of dead ends.

**What it requires.** The seam already exists: `AsyncOCRParser`, `SourceFormat.OCR`, `Block.confidence`, `Block.bbox`, `DocumentMetadata.ocr_confidence`, and the parser capability flags `ParserCapabilities.emits_confidence`, `ParserCapabilities.emits_bboxes`, `ParserCapabilities.is_async`, and `ParserCapabilities.requires_network`. The unresolved choices are the OCR engine, the job model, and the user experience for uncertainty.

Engine selection must compare Tesseract, PaddleOCR, and cloud APIs. Each option requires a license check. Cloud APIs also imply `ParserCapabilities.requires_network=True`, which is unacceptable for some air-gapped research environments and must be visible in `/api/v1/capabilities`.

OCR forces long-running work, so comparison and ingestion need a job queue rather than relying only on synchronous request handling. The UI must surface confidence: low-confidence blocks and tokens should look uncertain, not authoritative. Diffing OCR output also means diffing OCR errors as well as textual variation, so `Block.confidence`, `BoundingBox`, and warning display become part of the reading experience.

**Existing seam.** `backend/app/services/ingestion/base.py`, `AsyncDocumentParser`, `AsyncOCRParser`, `SourceFormat.OCR`, `Block.confidence`, `Block.bbox`, `DocumentMetadata.ocr_confidence`, `ParserCapabilities.emits_confidence`, `ParserCapabilities.emits_bboxes`, `ParserCapabilities.is_async`, and `ParserCapabilities.requires_network`.

### Multi-witness collation

**Motivation.** The real textual-criticism use case often has more than two witnesses. A scholar may want to compare a manuscript, a first edition, a revised edition, and a translation together.

**What it requires.** This is a genuine algorithmic step up. Pairwise collation does not generalize by running every pair and stacking the results. Multi-witness collation needs progressive or multiple sequence alignment over blocks and tokens, conflict handling, and a model for variants shared by some witnesses but not others.

`ComparisonResult` is pairwise by design: it has `a`, `b`, `a_tokens`, `b_tokens`, `a_index`, and `b_index`. A multi-witness result would need a generalized shape rather than overloading Manuscript A and Manuscript B fields.

**Existing seam.** The split between ingestion and diffing helps: every witness is already a canonical `Document`. The seam that must change is the pairwise `ComparisonResult` model and every frontend component that assumes two panes.

### Annotation and export

**Delivered.** TEI P5 export ships: `GET /api/v1/comparisons/{id}/export/tei` returns the collation using the parallel segmentation method, with structural relations as `<linkGrp>` in the back matter. See [ADR-0006](./adr/0006-tei-parallel-segmentation-export.md) and [API reference](./06-api-reference.md).

**Motivation.** Scholars do not only read differences; they explain them. Notes anchored to changed blocks make a comparison usable as scholarship rather than only as a reading.

**What it requires.** Margin notes should anchor to `Block` and character offsets. `Block.char_start` and `Block.char_end` already provide the core coordinate system. The annotation model must survive re-rendering, pagination changes, and view-mode changes. Annotations would also extend the TEI export, where `<note>` anchored to a block `@xml:id` is the natural encoding — which is part of why every exported block already carries one.

PDF and HTML exports remain open. They are reading artifacts rather than data artifacts, so each belongs at its own path under `/export/` with its own fidelity obligations; a single endpoint switching on format would let a lossy rendering inherit the guarantees of a lossless one.

**Existing seam.** `Block.id`, `Block.char_start`, `Block.char_end`, `DiffBlock.a_block_id`, `DiffBlock.b_block_id`, `group_id`, and `backend/app/services/formatting/{payload,tei}.py`.

### Persistence and accounts

**Motivation.** Saved projects require identity and persistence. Researchers need to return to a set of witnesses, annotations, and exports rather than relying on expiring URLs.

**What it requires.** This introduces authentication, authorization, privacy obligations, data retention policy, deletion policy, and a real database. It changes the security model from possession of an unguessable id to account-scoped access.

This is exactly why v1 avoids it. SQLite session storage with TTL is a deliberate boundary: useful for shareable comparisons, insufficient for saved scholarly projects, and small enough to avoid pretending that privacy and account management are solved.

**Existing seam.** `SessionStore` isolates storage operations. A persistent backend can replace `backend/app/storage/sqlite_store.py` if it preserves API semantics or explicitly changes them through an ADR.

### Independent pane scrolling

**Motivation.** Synoptic reading currently uses one virtualized list whose rows each hold Manuscript A, the connector and Manuscript B. Corresponding blocks therefore share a grid row and cannot drift apart, which is why no scroll synchronization is needed. The cost is that the panes move together: a researcher cannot hold chapter two of one witness beside chapter nine of the other.

**What it requires.** A second, deliberately different view with two independently scrolling virtualized panes. Once the panes can move apart, keeping them related again requires exactly the anchor-linked algorithm specified in [Components](./10-components.md): identify the leading visible aligned pair in the driving pane, compute fractional progress within it, and position the follower on its twin — never a pixel or percentage lock, which drifts within the first screenful. Virtualization makes it harder still, because the follower may have no measured row for the twin at the moment the driver reaches it, so positioning has to be approximate first and corrected once the real height is known.

**Existing seam.** `VirtualizedSynopticView` already isolates the reading surface behind a small handle, so an alternative view is an addition rather than a rewrite. `DiffBlock.a_index`, `b_index` and `group_id` supply the anchors.

### Alignment quality

**Delivered in part.** Verse is now segmented into one block per line, so poetry aligns at the line rather than the stanza and a transposed line reports as `MOVED`. A repeated refrain does not confuse alignment. Stanza boundaries survive segmentation, so a poem re-divided between drafts reports the change rather than reading as identical. See [Normalization](./03-normalization.md) and [ADR-0007](./adr/0007-stanza-boundaries.md).

**Motivation.** Heavily rewritten passages, drama, and repetitive text still expose the limits of block similarity plus LIS move detection.

**What it requires.** Semantic or embedding-assisted alignment may help match paraphrased or heavily revised blocks, but it must not turn the tool into meaning-level diffing. Drama needs structure-aware segmentation so speaker labels and stage directions are not compared as if they were dialogue. User-correctable alignment would let a scholar override a bad match; those corrections could also become training data for future alignment heuristics.

One verse-specific gap remains: verse whose lines run long, much blank verse among it, falls outside the conservative detection threshold and is read as prose. That wants evidence from real use before anyone tunes a threshold, because the cost of loosening it is shredding paragraphs.

A second is narrower and known. A poem written in Word with one paragraph per line — pressing Enter rather than Shift+Enter — aligns correctly line by line but keeps `PARAGRAPH` as its kind, so it gets neither verse typography nor `<l>` in the TEI export. Detecting verse *across* sibling blocks is a different heuristic from detecting it within one, and a riskier one: a list, a run of short paragraphs, or dialogue would all be candidates. It needs its own evidence rather than an extension of the current rule.

**Existing seam.** `backend/app/services/diffing/alignment.py`, `DiffOptions.align_threshold`, `DiffOptions.move_threshold`, `DiffOptions.detect_moves`, `DiffBlock.group_id`, `BlockKind.VERSE_LINE`, and URL state `?moves=on|off`.

### Scale

**Motivation.** SQLite is the right v1 session cache, but it has a single writer. Horizontal scaling needs a networked storage backend and a queue-aware execution model.

**What it requires.** Swap `SessionStore` for a networked backend while preserving TTL semantics, unguessable ids, RFC 9457 error behaviour, and serialized `ComparisonResult` access. Large deployments also need distributed sweeping or native expiry, request coordination, and background job state for accepted comparisons.

**Existing seam.** `SessionStore`, `backend/app/storage/{store,sqlite_store,sweeper}.py`, `ComparisonResult.truncated`, `BlockPage`, and the `202` accepted polling path.

## Explicitly not planned

| Not planned | Reason |
|---|---|
| Becoming a merge or editing tool | palimpsest reads variation; it does not produce an authoritative combined text. |
| Semantic meaning-level diffing | The tool compares witness text and structure, not inferred meaning. |
| Real-time collaboration | It would require accounts, presence, conflict resolution, and a different product boundary. |
| Hosting a public corpus of user uploads | User witnesses may be unpublished, copyrighted, or sensitive; v1 uses TTL storage and no public library. |

## How to propose a change

Propose contract, dependency, storage, or architecture changes through [ADR index](./adr/README.md). A good ADR states the problem, the decision, the alternatives rejected, the license and privacy implications, and the exact contracts affected.
