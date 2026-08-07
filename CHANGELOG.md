# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added

- Upload and parse `.txt`, `.md`, `.docx`, and `.pdf` witnesses, with honest refusal of scanned PDFs that require OCR.
- Normalize prose with Unicode cleanup, line reflow, dehyphenation, and verse-aware segmentation.
- Compare witnesses with word-level diffing, metrics, moved-block detection, and split/merge grouping.
- Persist expiring comparison sessions in SQLite and expose the REST API for documents, comparisons, capabilities, health, and TEI export.
- Render a typography-first frontend with manuscript upload, synoptic and unified reading modes, structural markers, change navigation, block deep links, and print styles.
- Virtualize long comparisons and fetch windowed blocks so large witnesses remain readable.
- Export comparisons as TEI P5 with structural relations encoded in the back matter.

### Fixed

- Prevent Markdown container syntax from fabricating prose joins the specification forbids.
- Keep deep-link focus stable when virtualized target rows mount later.
- Key virtualized rows by block id rather than index to avoid stale rendering.
- Handle accepted asynchronous comparisons in the frontend instead of treating `202` as an error.
- Bound ingestion cost for decompressed uploads and very large PDFs.
- Remove XML-forbidden control characters from canonical text and titles so TEI exports remain parseable.
- Regenerate API types when backend response paths changed.

### Changed

- Treat `docs/` as the normative specification and record contested architectural choices as ADRs.
- Use server-side diff computation and a SQLite TTL store for shareable expiring comparison URLs.
- Adopt Tailwind v4 CSS-first design tokens for the manuscript visual system.
- Generate frontend API types from the backend OpenAPI schema and check for drift in CI.
- Regenerate the frontend lockfile on Linux with canonical npm registry URLs so CI and local installs agree.
