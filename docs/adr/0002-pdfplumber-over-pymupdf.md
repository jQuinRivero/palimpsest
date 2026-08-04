# ADR-0002 — Use pdfplumber for PDF extraction

**Status:** Accepted
**Related:** [Ingestion and parsers](../02-ingestion-and-parsers.md) · [Edge cases](../12-edge-cases.md) · [Testing strategy](../13-testing-strategy.md)

## Context

PDF text extraction quality directly determines diff quality. A bad extraction produces phantom changes, especially when reading order, running heads, folio numbers, hyphenation, or column layout are misread. `PyMuPDF` 1.28.0 is, by a clear technical margin, the strongest option: MuPDF's C engine is fast, its `get_text("dict")` output exposes a rich block, line, and span hierarchy, and its reading-order behaviour is best in class.

The blocker is license compatibility. `PyMuPDF` is AGPL-3.0, while this repository is Apache-2.0. Shipping an AGPL dependency would make the effective combined work AGPL for deployment, and network use triggers source-provision obligations. That would silently change the license users think they are getting and would prevent downstream reuse under Apache-2.0 terms. Artifex sells a commercial license, but that is not appropriate for a community open-source project.

## Options considered

- `pdfplumber` 0.11.x. It is MIT, active, built on `pdfminer.six`, and exposes character-level positional data. Its `extract_text(layout=True)` mode gives the parser enough layout signal to classify likely prose, page artefacts, and extraction warnings.
- `pypdf` 6.14.2. It is BSD-3, pure Python, and fast on simple well-formed PDFs. Its extraction model is weaker for complex layouts, but it is attractive as a permissive fast path.
- `PyMuPDF` 1.28.0. It is the technically best extractor for the product, especially for block hierarchy and reading order, but AGPL-3.0 is incompatible with the project's Apache-2.0 distribution goals.
- A commercial MuPDF license. This would remove the AGPL blocker and preserve the best technical option, but it would make a core capability depend on a paid arrangement that cannot be assumed for community contributors or downstream users.

## Decision

Use `pdfplumber` 0.11.x as the default `PdfPlumberParser`. Register `pypdf` 6.14.2 as `PyPdfParser` for a fast path on simple well-formed PDFs.

This ADR also sets the general dependency rule for `palimpsest`: any proposed dependency must state its license, and copyleft is disqualifying under Apache-2.0.

## Consequences

We are knowingly giving up the better PDF extractor. Complex layouts will produce worse extraction than `PyMuPDF`, which is why [Edge cases](../12-edge-cases.md) maintains a catalogue of PDF failure modes, why `ARTIFACT` block classification exists for extracted running heads and folio material, and why `PdfPlumberParser` declares `is_lossy=True`.

The benefit is that the project remains Apache-2.0 without hidden copyleft obligations, and downstream users can reuse the application under the license they expect. Revisit this decision if a permissively licensed extractor of comparable quality appears, or if the project receives a sustainable licensing arrangement that still preserves Apache-2.0 reuse for all downstream users.

## The general rule this record sets

Any proposed dependency must state its license, and **strong copyleft — GPL-2.0, GPL-3.0, AGPL-3.0 — is disqualifying**, transitively as well as directly. `backend/scripts/check_licences.py` enumerates every installed distribution and fails the build on a strong-copyleft match, so this is enforced rather than merely intended.

**Weak, file-level copyleft is assessed rather than banned.** MPL-2.0 obliges sharing modifications to the MPL-licensed *files*; it does not reach the combined work. Three MPL-2.0 packages are currently present and each is acceptable for a specific reason: `certifi` is a CA certificate data bundle we never modify, and `hypothesis` and `pathspec` are development-only and never distributed with the application. The script reports these for review rather than blocking, and adding a *runtime* MPL dependency should prompt a new record.

The following are rejected on license grounds and must not be reintroduced: `PyMuPDF` (AGPL-3.0), `python-Levenshtein` (GPL-2.0 — `rapidfuzz` covers the same ground under MIT), and `dehyphen` (GPL-3.0, and stale besides).
