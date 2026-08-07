# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added

- Upload and parse `.txt`, `.md`, `.docx`, and `.pdf` witnesses, with honest refusal of scanned PDFs that require OCR.
- Normalize prose with Unicode cleanup, line reflow, dehyphenation, and verse-aware segmentation.
- Compare witnesses with word-level diffing, metrics, moved-block detection, and split/merge grouping.
- Create shareable expiring comparison URLs and expose API endpoints for documents, comparisons, capabilities, health, and TEI export.
- Render a typography-first frontend with manuscript upload, synoptic and unified reading modes, structural markers, change navigation, block deep links, and print styles.
- Virtualize long comparisons and fetch windowed blocks so large witnesses remain readable.
- Export comparisons as TEI P5 with structural relations encoded in the back matter.

### Fixed

- Prevent Markdown container syntax from fabricating prose joins the specification forbids.
- Keep deep-link focus stable when virtualized target rows mount later.
- Key virtualized rows by block id rather than index to avoid stale rendering.
- Handle accepted asynchronous comparisons in the frontend instead of treating `202` as an error.
- Refuse decompressed uploads and very large PDFs before they exhaust the parser budget.
- Remove XML-forbidden control characters from canonical text and titles so TEI exports remain parseable.
