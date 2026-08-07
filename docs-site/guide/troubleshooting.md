# Troubleshooting

palimpsest returns RFC 9457 `application/problem+json` errors with a stable `code`.

| Code | Meaning | What to do |
|---|---|---|
| `UNSUPPORTED_FORMAT` | No registered parser can safely parse the upload, or the signals conflict. | Export to `.txt`, `.md`, `.docx`, or a text-bearing `.pdf`, then upload again. |
| `OCR_REQUIRED` | The PDF appears to be scanned and has no extractable text. | Run OCR outside palimpsest or export searchable text; OCR does not ship in v1. |
| `EMPTY_DOCUMENT` | The upload parsed to no usable text. | Check that the file contains main-body text and is not only images, comments, or metadata. |
| `FILE_TOO_LARGE` | The upload exceeds the server limit. | Use a smaller witness or split the source before upload. |
| `COMPARISON_EXPIRED` | The comparison existed but its TTL has passed. | Re-upload the witnesses and create a new comparison. |

Other API errors exist for malformed documents, missing IDs, rate limiting, budget limits, and internal failures. This page focuses on the user-facing cases most likely during upload and reading.

Normative detail: [API reference](https://github.com/jQuinRivero/palimpsest/blob/main/docs/06-api-reference.md).
