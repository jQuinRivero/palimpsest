---
title: "palimpsest: typography-first collation for reading literary revision"
tags:
  - digital humanities
  - textual criticism
  - textual scholarship
  - scholarly editing
  - collation
  - TEI
  - Python
authors:
  - name: Joaquín Rivero
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: Independent researcher
    index: 1
date: 1 January 2026
bibliography: paper.bib
---

# Summary

`palimpsest` compares two witnesses of a literary text and presents the result
as something a person can read. It aligns passages before it compares words, so
a paragraph that was moved is reported as a move, a paragraph that was split is
reported as a split, and only genuinely rewritten wording is marked as
insertion or deletion. Poetry is compared line by line, preserving stanza
boundaries. A comparison can be read side by side or as a single stream, cited
by passage, and exported as TEI P5 using parallel segmentation [@tei].

The software takes two documents in `.txt`, `.md`, `.docx`, or `.pdf` form and
requires no prior encoding. It runs locally: manuscripts are never transmitted
to a third party, which matters when the text under study is unpublished.

# Statement of need

Scholars who need to see what changed between two versions of a text are served
either by collation engines built for producing an apparatus, or by comparison
tools built for source code. Neither is designed for reading.

Collation in the digital humanities is mature. CollateX [@collatex] implements
the Gothenburg model [@gothenburg] and aligns arbitrarily many witnesses into
variant graphs and alignment tables; Juxta [@juxta] provides collation with
heat-map visualisation; the Versioning Machine [@vmachine] displays TEI
parallel segmentation that an editor has already encoded. These tools answer
the question an editor asks while building an apparatus criticus. They assume
either prior TEI encoding, or an interest in the alignment itself as an object
of study.

The complementary question is the one a critic asks while reading: what did the
author actually do to this passage? Answering it with a general-purpose diff is
actively misleading. Line-oriented tools such as `diff` treat prose as physical
lines, so reflowing a paragraph reports the whole paragraph as rewritten.
Because such tools have no notion of a passage, a relocated section is reported
as a deletion in one place and an unrelated insertion in another — precisely
the relationship the reader wanted preserved. Word-processor comparison shares
the second limitation. The result inflates the apparent volume of revision and
conceals its structure.

`palimpsest` separates the two questions the reader is really asking.
Structural change — moved, split, merged — is detected over aligned passages,
described in prose, and deliberately excluded from the wording-change metrics.
Word-level revision is then computed only where wording genuinely differs,
using a token-level diff [@dmp] with fuzzy passage matching [@rapidfuzz]. A
paragraph that moved unchanged therefore contributes zero insertions and zero
deletions, and is reported as a move.

The remaining design commitment is typographic. Change is shown in the reading
face rather than in a monospaced patch, marked with `+` and `−` cues and
token-bounded highlights rather than by colour alone, with keyboard navigation
between changes, screen-reader announcements, and greyscale print styles. This
follows the accessibility requirement that colour never be the sole carrier of
meaning [@wcag]. Long witnesses are virtualised and paged, so a full-length
novel remains responsive.

The intended users are textual critics, literary scholars, editors, translators
comparing revisions, and students learning to read variants. The scope is
deliberately narrow: two witnesses, local or trusted deployment, no user
accounts, no bundled OCR, and no multi-user editorial workspace. Projects
needing an apparatus across many witnesses are better served by CollateX, and
`palimpsest` is designed to hand off to that ecosystem rather than duplicate
it — its TEI P5 output is intended as an entry point to existing editorial
tooling.

# Implementation

The backend is a Python 3.12 FastAPI service with a SQLite session store; the
reading interface is a Next.js and React application. Collation is computed
on the server and delivered as a structured payload, so the browser renders a
comparison rather than reimplementing the algorithm. That keeps a single
normative implementation and lets the same payload drive the TEI export.
Comparisons are a cache with a deadline rather than a system of record: the
researcher's own files remain authoritative.

The project ships a normative specification, architecture decision records for
each significant choice, property-based and end-to-end test suites, and a
container image so that readers without a Python or Node toolchain can run it
with a single command.

# Acknowledgements

`palimpsest` builds on the diff-match-patch algorithms [@dmp], RapidFuzz
[@rapidfuzz], and the TEI Guidelines [@tei].

# References
