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

Existing hardening includes bounded upload expansion and page counts. Parsers refuse sources that exceed the default decompressed-size budget of 128 MiB or the default PDF page-count budget of 5000 pages; see `backend/app/services/ingestion/base.py`.

There is no authentication and no multi-tenancy. Reports such as "another user can read my comparison" are therefore outside the current threat model: comparisons are shareable expiring URLs by design. Security reports should focus on issues such as arbitrary file access, code execution, denial of service beyond documented limits, unsafe parsing behavior, dependency vulnerabilities, or disclosure outside the intended share URL model.
