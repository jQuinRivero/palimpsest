# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

Nothing has been released yet; this policy applies to the current `0.1.x` line while the repository is prepared for public release.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**. That keeps the report private while it is triaged and fixed.

If GitHub private reporting is unavailable, open a minimal public issue asking for a private contact path without disclosing exploit details.

## Scope and threat model

`palimpsest` is a local document-processing web app. Its highest-risk surface is hostile input: `.docx` files are ZIP containers, and `.pdf` is a complex format with a long history of parser bugs.

Existing hardening includes bounded upload expansion and page counts. The defaults are a decompressed-size budget of 128 MiB and a PDF page-count budget of 5000 pages; see `DEFAULT_MAX_DECOMPRESSED_BYTES` and `DEFAULT_MAX_PAGES` in `backend/app/services/ingestion/base.py`. The upload endpoint enforces the configured settings by passing `PALIMPSEST_MAX_DECOMPRESSED_BYTES` and `PALIMPSEST_MAX_PDF_PAGES` (`max_decompressed_bytes` and `max_pdf_pages` in `backend/app/config.py`) into each parser and returning `FILE_TOO_LARGE` when a source exceeds them. Operators who raise those settings also raise the document-parsing denial-of-service budget.

There is no authentication and no multi-tenancy. Reports such as "another user can read my comparison" are therefore outside the current threat model: comparisons are shareable expiring URLs by design. Security reports should focus on issues such as arbitrary file access, code execution, denial of service beyond documented limits, unsafe parsing behavior, dependency vulnerabilities, or disclosure outside the intended share URL model.
