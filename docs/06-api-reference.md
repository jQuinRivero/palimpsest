This document defines the HTTP API for uploading witnesses, running a collation, reading comparison blocks, and discovering server capabilities.

**Status:** Draft

**Related:** [Spec index](./README.md) · [Data schema](./05-data-schema.md) · [Session storage](./07-session-storage.md) · [Performance and scale](./11-performance-and-scale.md) · [Testing strategy](./13-testing-strategy.md)

## Conventions

The API base path is `/api/v1`. The API is path-versioned: incompatible changes require a new major path such as `/api/v2`; changes within `/api/v1` are additive only and must not remove fields, rename fields, change enum values, or narrow accepted inputs.

JSON field names are `snake_case`, matching the Python Pydantic models without aliasing. Timestamps are RFC 3339 UTC strings with a `Z` suffix. Identifiers are URL-safe, unguessable strings produced from 128 bits of cryptographically secure randomness, for example `secrets.token_urlsafe(16)` in Python. Unguessability is the whole access-control model in v1: there are no accounts, permissions, or sharing grants, so possession of a document or comparison id is possession of access until the row expires.

Requests and responses use `application/json` except `POST /api/v1/documents`, which uses `multipart/form-data`, and errors, which use `application/problem+json`.

Responses that expose comparison ids or comparison content (`ComparisonResult`, `ComparisonAccepted`, and `BlockPage`) set `X-Robots-Tag: noindex` and `Cache-Control: private, no-store`.

## Endpoint summary

| Method | Path | Body or query | Success response |
|---|---|---|---|
| `POST` | `/api/v1/documents` | multipart `file`, optional `title` | `201 DocumentSummary` |
| `GET` | `/api/v1/documents/{document_id}` | — | `200 Document` |
| `DELETE` | `/api/v1/documents/{document_id}` | — | `204 No Content` |
| `POST` | `/api/v1/comparisons` | `{a_document_id, b_document_id, options?}` | `201 ComparisonResult` or `202 ComparisonAccepted` |
| `GET` | `/api/v1/comparisons/{comparison_id}` | `include_blocks` | `200 ComparisonResult` or `202 ComparisonAccepted` while pending |
| `GET` | `/api/v1/comparisons/{comparison_id}/blocks` | `offset`, `limit` | `200 BlockPage` |
| `GET` | `/api/v1/comparisons/{comparison_id}/export/tei` | — | `200 application/tei+xml` or `202 ComparisonAccepted` while pending |
| `DELETE` | `/api/v1/comparisons/{comparison_id}` | — | `204 No Content` |
| `GET` | `/api/v1/capabilities` | — | `200 CapabilitiesResponse` |
| `GET` | `/api/v1/health` | — | `200 HealthResponse` |

## `POST /api/v1/documents`

Uploads one witness, parses it, stores the parsed `Document`, and returns a `DocumentSummary`.

### Request

| Part or header | Required | Meaning |
|---|---:|---|
| `Content-Type: multipart/form-data` | yes | Multipart request body |
| `file` | yes | The witness bytes |
| `title` | no | Human-readable title; defaults to the uploaded filename without path |

FastAPI receives `file` as an `UploadFile` backed by `SpooledTemporaryFile`: small uploads stay in memory and larger uploads spill to disk after a threshold. That matters for large manuscripts because the server can stream parser input without loading the entire witness into RAM. The v1 maximum upload size is 25 MiB per witness. The limit is enforced at the ASGI/middleware layer by inspecting `Content-Length` and by counting streamed bytes, because `Content-Length` is client-supplied and can lie.

### Example request

```http
POST /api/v1/documents HTTP/1.1
Host: localhost:8000
Content-Type: multipart/form-data; boundary=palimpsest-boundary

--palimpsest-boundary
Content-Disposition: form-data; name="title"

Manuscript A
--palimpsest-boundary
Content-Disposition: form-data; name="file"; filename="manuscript-a.txt"
Content-Type: text/plain

It was the best of times.
It was the worst of times.
--palimpsest-boundary--
```

### Success response

`201 Created`

```json
{
  "id": "doc_rV3xYlKq9n4Q",
  "title": "Manuscript A",
  "source_format": "TXT",
  "metadata": {
    "word_count": 12,
    "block_count": 2,
    "char_count": 52,
    "detected_language": "en",
    "parser_name": "PlainTextParser",
    "parser_version": "1.0.0",
    "ocr_confidence": null
  },
  "warnings": []
}
```

### Errors

`UNSUPPORTED_FORMAT`, `FILE_TOO_LARGE`, `MALFORMED_DOCUMENT`, `EMPTY_DOCUMENT`, `OCR_REQUIRED`, `RATE_LIMITED`, `INTERNAL_ERROR`.

## `GET /api/v1/documents/{document_id}`

Returns the parsed `Document` for one uploaded witness.

### Request

| Parameter | Required | Meaning |
|---|---:|---|
| `document_id` | yes | Unguessable document id |

### Example request

```http
GET /api/v1/documents/doc_rV3xYlKq9n4Q HTTP/1.1
Host: localhost:8000
Accept: application/json
```

### Success response

`200 OK`

```json
{
  "id": "doc_rV3xYlKq9n4Q",
  "title": "Manuscript A",
  "source_format": "TXT",
  "blocks": [
    {
      "id": "blk_a_0000",
      "index": 0,
      "kind": "PARAGRAPH",
      "text": "It was the best of times.",
      "style": null,
      "page": null,
      "char_start": 0,
      "char_end": 25,
      "confidence": null,
      "bbox": null
    },
    {
      "id": "blk_a_0001",
      "index": 1,
      "kind": "PARAGRAPH",
      "text": "It was the worst of times.",
      "style": null,
      "page": null,
      "char_start": 26,
      "char_end": 52,
      "confidence": null,
      "bbox": null
    }
  ],
  "metadata": {
    "word_count": 12,
    "block_count": 2,
    "char_count": 52,
    "detected_language": "en",
    "parser_name": "PlainTextParser",
    "parser_version": "1.0.0",
    "ocr_confidence": null
  },
  "warnings": []
}
```

### Errors

`DOCUMENT_NOT_FOUND`, `RATE_LIMITED`, `INTERNAL_ERROR`.

## `DELETE /api/v1/documents/{document_id}`

Deletes one stored witness. Comparisons that reference it are deleted by cascade.

### Request

| Parameter | Required | Meaning |
|---|---:|---|
| `document_id` | yes | Unguessable document id |

### Example request

```http
DELETE /api/v1/documents/doc_rV3xYlKq9n4Q HTTP/1.1
Host: localhost:8000
```

### Success response

`204 No Content`

### Errors

`DOCUMENT_NOT_FOUND`, `RATE_LIMITED`, `INTERNAL_ERROR`.

## `POST /api/v1/comparisons`

Creates a collation between Manuscript A and Manuscript B. The request body references two existing documents and optional `DiffOptions`.

### Request

| Header | Required | Meaning |
|---|---:|---|
| `Content-Type: application/json` | yes | JSON request body |

```json
{
  "a_document_id": "doc_rV3xYlKq9n4Q",
  "b_document_id": "doc_bK8mN2pQ5sV6",
  "options": {
    "granularity": "WORD",
    "detect_moves": true,
    "align_threshold": 0.5,
    "move_threshold": 0.75,
    "ignore_case": false,
    "ignore_punctuation": false,
    "normalize_whitespace": true
  }
}
```

Omit `options` to use the current defaults advertised by `GET /api/v1/capabilities`.

### Example request

```http
POST /api/v1/comparisons HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Accept: application/json

{"a_document_id":"doc_rV3xYlKq9n4Q","b_document_id":"doc_bK8mN2pQ5sV6","options":{"granularity":"WORD","detect_moves":true,"align_threshold":0.5,"move_threshold":0.75,"ignore_case":false,"ignore_punctuation":false,"normalize_whitespace":true}}
```

### Success response: synchronous

`201 Created`

```json
{
  "comparison_id": "cmp_P7nR4tV9xA2mQ6s",
  "created_at": "2026-08-04T13:16:05Z",
  "expires_at": "2026-08-11T13:16:05Z",
  "a": {
    "id": "doc_rV3xYlKq9n4Q",
    "title": "Manuscript A",
    "source_format": "TXT",
    "metadata": {
      "word_count": 12,
      "block_count": 2,
      "char_count": 52,
      "detected_language": "en",
      "parser_name": "PlainTextParser",
      "parser_version": "1.0.0",
      "ocr_confidence": null
    },
    "warnings": []
  },
  "b": {
    "id": "doc_bK8mN2pQ5sV6",
    "title": "Manuscript B",
    "source_format": "TXT",
    "metadata": {
      "word_count": 12,
      "block_count": 2,
      "char_count": 57,
      "detected_language": "en",
      "parser_name": "PlainTextParser",
      "parser_version": "1.0.0",
      "ocr_confidence": null
    },
    "warnings": []
  },
  "blocks": [
    {
      "id": "dbk_0001",
      "status": "MODIFIED",
      "kind": "PARAGRAPH",
      "a_index": 0,
      "b_index": 0,
      "a_block_id": "blk_a_0000",
      "b_block_id": "blk_b_0000",
      "tokens": [
        {"text": "It ", "status": "UNCHANGED"},
        {"text": "was ", "status": "UNCHANGED"},
        {"text": "the ", "status": "UNCHANGED"},
        {"text": "best ", "status": "DELETION"},
        {"text": "brightest ", "status": "INSERTION"},
        {"text": "of ", "status": "UNCHANGED"},
        {"text": "times.", "status": "UNCHANGED"}
      ],
      "a_tokens": [
        {"text": "It ", "status": "UNCHANGED"},
        {"text": "was ", "status": "UNCHANGED"},
        {"text": "the ", "status": "UNCHANGED"},
        {"text": "best ", "status": "DELETION"},
        {"text": "of ", "status": "UNCHANGED"},
        {"text": "times.", "status": "UNCHANGED"}
      ],
      "b_tokens": [
        {"text": "It ", "status": "UNCHANGED"},
        {"text": "was ", "status": "UNCHANGED"},
        {"text": "the ", "status": "UNCHANGED"},
        {"text": "brightest ", "status": "INSERTION"},
        {"text": "of ", "status": "UNCHANGED"},
        {"text": "times.", "status": "UNCHANGED"}
      ],
      "metrics": {
        "similarity": 0.9091,
        "edit_count": 2,
        "insertions": 1,
        "deletions": 1,
        "churn": 0.1667
      },
      "move_distance": null,
      "group_id": null
    },
    {
      "id": "dbk_0002",
      "status": "UNCHANGED",
      "kind": "PARAGRAPH",
      "a_index": 1,
      "b_index": 1,
      "a_block_id": "blk_a_0001",
      "b_block_id": "blk_b_0001",
      "tokens": [
        {"text": "It was the worst of times.", "status": "UNCHANGED"}
      ],
      "a_tokens": [
        {"text": "It was the worst of times.", "status": "UNCHANGED"}
      ],
      "b_tokens": [
        {"text": "It was the worst of times.", "status": "UNCHANGED"}
      ],
      "metrics": {
        "similarity": 1.0,
        "edit_count": 0,
        "insertions": 0,
        "deletions": 0,
        "churn": 0.0
      },
      "move_distance": null,
      "group_id": null
    }
  ],
  "metrics": {
    "similarity": 0.9167,
    "edit_count": 2,
    "insertions": 1,
    "deletions": 1,
    "unchanged_tokens": 11,
    "churn": 0.0833,
    "blocks_moved": 0,
    "blocks_split": 0,
    "blocks_merged": 0,
    "a_word_count": 12,
    "b_word_count": 12
  },
  "options": {
    "granularity": "WORD",
    "detect_moves": true,
    "align_threshold": 0.5,
    "move_threshold": 0.75,
    "ignore_case": false,
    "ignore_punctuation": false,
    "normalize_whitespace": true
  },
  "truncated": false,
  "total_blocks": 2
}
```

### Success response: accepted for asynchronous completion

`202 Accepted`

Large manuscripts that exceed the synchronous diff budget but remain within the absolute limits in [Performance and scale](./11-performance-and-scale.md) return `ComparisonAccepted`.

```json
{
  "comparison_id": "cmp_mD2qS8vW1xY6zA3bC9eF",
  "status": "PENDING",
  "created_at": "2026-08-04T13:16:05Z",
  "expires_at": "2026-08-11T13:16:05Z",
  "retry_after": 2
}
```

Clients poll `GET /api/v1/comparisons/{comparison_id}`. While `status` is `PENDING`, the server returns `202 Accepted` with the same `ComparisonAccepted` shape and may increase `retry_after`. Clients should use exponential backoff beginning at 2 seconds, cap it at 15 seconds, and stop polling when the comparison returns `200 OK`, `COMPARISON_EXPIRED`, or `COMPARISON_NOT_FOUND`.

### Errors

`DOCUMENT_NOT_FOUND`, `DIFF_BUDGET_EXCEEDED`, `COMPARISON_EXPIRED`, `RATE_LIMITED`, `INTERNAL_ERROR`.

## `GET /api/v1/comparisons/{comparison_id}`

Returns a comparison. By default it includes blocks; clients that only need summary metadata may pass `include_blocks=false`.

These headers matter because comparison ids are bearer links to unpublished witness text, not because they provide authorization.

### Request

| Parameter | Required | Meaning |
|---|---:|---|
| `comparison_id` | yes | Unguessable comparison id |
| `include_blocks` | no | Boolean; defaults to `true` |

### Example request

```http
GET /api/v1/comparisons/cmp_P7nR4tV9xA2mQ6s?include_blocks=false HTTP/1.1
Host: localhost:8000
Accept: application/json
```

### Success response

`200 OK`

```json
{
  "comparison_id": "cmp_P7nR4tV9xA2mQ6s",
  "created_at": "2026-08-04T13:16:05Z",
  "expires_at": "2026-08-11T13:16:05Z",
  "a": {
    "id": "doc_rV3xYlKq9n4Q",
    "title": "Manuscript A",
    "source_format": "TXT",
    "metadata": {
      "word_count": 12,
      "block_count": 2,
      "char_count": 52,
      "detected_language": "en",
      "parser_name": "PlainTextParser",
      "parser_version": "1.0.0",
      "ocr_confidence": null
    },
    "warnings": []
  },
  "b": {
    "id": "doc_bK8mN2pQ5sV6",
    "title": "Manuscript B",
    "source_format": "TXT",
    "metadata": {
      "word_count": 12,
      "block_count": 2,
      "char_count": 57,
      "detected_language": "en",
      "parser_name": "PlainTextParser",
      "parser_version": "1.0.0",
      "ocr_confidence": null
    },
    "warnings": []
  },
  "blocks": [],
  "metrics": {
    "similarity": 0.9167,
    "edit_count": 2,
    "insertions": 1,
    "deletions": 1,
    "unchanged_tokens": 11,
    "churn": 0.0833,
    "blocks_moved": 0,
    "blocks_split": 0,
    "blocks_merged": 0,
    "a_word_count": 12,
    "b_word_count": 12
  },
  "options": {
    "granularity": "WORD",
    "detect_moves": true,
    "align_threshold": 0.5,
    "move_threshold": 0.75,
    "ignore_case": false,
    "ignore_punctuation": false,
    "normalize_whitespace": true
  },
  "truncated": true,
  "total_blocks": 2
}
```

### Pending response

`202 Accepted` with `ComparisonAccepted`, as described for `POST /api/v1/comparisons`.

### Errors

`COMPARISON_NOT_FOUND`, `COMPARISON_EXPIRED`, `RATE_LIMITED`, `INTERNAL_ERROR`.

## `GET /api/v1/comparisons/{comparison_id}/blocks`

Returns a window of `DiffBlock` values for the virtualized client. This is the preferred read path for very long manuscripts.

### Request

| Parameter | Required | Meaning |
|---|---:|---|
| `comparison_id` | yes | Unguessable comparison id |
| `offset` | no | Zero-based block offset; defaults to `0` |
| `limit` | no | Number of blocks to return; defaults to `200`; maximum `500` |

`offset` is applied to the stable `blocks` order in `ComparisonResult`. `limit` is clamped to the maximum; negative values are rejected as malformed query parameters.

### Example request

```http
GET /api/v1/comparisons/cmp_P7nR4tV9xA2mQ6s/blocks?offset=0&limit=1 HTTP/1.1
Host: localhost:8000
Accept: application/json
```

### Success response

`200 OK`

```json
{
  "blocks": [
    {
      "id": "dbk_0001",
      "status": "MODIFIED",
      "kind": "PARAGRAPH",
      "a_index": 0,
      "b_index": 0,
      "a_block_id": "blk_a_0000",
      "b_block_id": "blk_b_0000",
      "tokens": [
        {"text": "It ", "status": "UNCHANGED"},
        {"text": "was ", "status": "UNCHANGED"},
        {"text": "the ", "status": "UNCHANGED"},
        {"text": "best ", "status": "DELETION"},
        {"text": "brightest ", "status": "INSERTION"},
        {"text": "of ", "status": "UNCHANGED"},
        {"text": "times.", "status": "UNCHANGED"}
      ],
      "a_tokens": [
        {"text": "It ", "status": "UNCHANGED"},
        {"text": "was ", "status": "UNCHANGED"},
        {"text": "the ", "status": "UNCHANGED"},
        {"text": "best ", "status": "DELETION"},
        {"text": "of ", "status": "UNCHANGED"},
        {"text": "times.", "status": "UNCHANGED"}
      ],
      "b_tokens": [
        {"text": "It ", "status": "UNCHANGED"},
        {"text": "was ", "status": "UNCHANGED"},
        {"text": "the ", "status": "UNCHANGED"},
        {"text": "brightest ", "status": "INSERTION"},
        {"text": "of ", "status": "UNCHANGED"},
        {"text": "times.", "status": "UNCHANGED"}
      ],
      "metrics": {
        "similarity": 0.9091,
        "edit_count": 2,
        "insertions": 1,
        "deletions": 1,
        "churn": 0.1667
      },
      "move_distance": null,
      "group_id": null
    }
  ],
  "offset": 0,
  "limit": 1,
  "total_blocks": 2
}
```

### Errors

`COMPARISON_NOT_FOUND`, `COMPARISON_EXPIRED`, `RATE_LIMITED`, `INTERNAL_ERROR`.

## `GET /api/v1/comparisons/{comparison_id}/export/tei`

Exports the collation as a TEI P5 document using the parallel segmentation method. See [ADR-0006](./adr/0006-tei-parallel-segmentation-export.md) for why that method, and for how structural relations are encoded.

### Request

| Parameter | Required | Meaning |
|---|---:|---|
| `comparison_id` | yes | Unguessable comparison id |

### Example request

```http
GET /api/v1/comparisons/cmp_P7nR4tV9xA2mQ6s/export/tei HTTP/1.1
Host: localhost:8000
```

### Success response

`200 OK`, `Content-Type: application/tei+xml`, `Content-Disposition: attachment; filename="palimpsest-{comparison_id}.xml"`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Collation of draft-1.txt and draft-2.txt</title>
      </titleStmt>
      <publicationStmt>
        <p>Generated by palimpsest. This file records a collation of two witnesses and is not an edition: no reading is presented as authoritative, and the witnesses are given in upload order rather than in any stemmatic relation.</p>
      </publicationStmt>
      <sourceDesc>
        <listWit>
          <witness xml:id="A">draft-1.txt (TXT)</witness>
          <witness xml:id="B">draft-2.txt (TXT)</witness>
        </listWit>
      </sourceDesc>
    </fileDesc>
    <encodingDesc>
      <variantEncoding method="parallel-segmentation" location="internal" />
      <p>Collated automatically at word granularity. Similarity 0.966; 1 word inserted, 1 word deleted, 28 words unchanged. 1 block moved, 2 blocks split, 0 blocks merged. Structural relations between blocks are recorded as linkGrp elements in the back matter, because the TEI apparatus module describes variation in reading rather than transposition of passages.</p>
    </encodingDesc>
  </teiHeader>
  <text>
    <body>
      <p xml:id="blk-dbk_0001">It was a long crossing. </p>
      <p xml:id="blk-dbk_0002">The waves were <app><rdg wit="#A">grey </rdg><rdg wit="#B">slate </rdg></app>from the first morning.</p>
    </body>
    <back>
      <linkGrp type="split">
        <link target="#blk-dbk_0001 #blk-dbk_0002" />
      </linkGrp>
    </back>
  </text>
</TEI>
```

### Guarantees

| Guarantee | Meaning |
|---|---|
| Reconstruction | Selecting every `<rdg wit="#A">` and concatenating reproduces the Manuscript A pane word for word, and likewise for B. This is what makes the file an archive rather than a rendering. |
| Element identity | Every block element carries `@xml:id` derived from `DiffBlock.id`, so citations and `<link>` targets are stable. |
| Structural relations | `MOVED`, `SPLIT`, and `MERGED` appear as `<linkGrp type="moved\|split\|merged">` in `<back>`. One split is one `<link>` naming every member, not one link per member. |
| Completeness | A windowed or still-pending comparison is never exported. A truncated screen shows the reader it is truncated; a TEI file does not. |

### Pending response

`202 Accepted` with a `ComparisonAccepted` body and a `Retry-After` header, using the same shape as `GET /api/v1/comparisons/{comparison_id}`.

### Errors

`COMPARISON_NOT_FOUND`, `COMPARISON_EXPIRED`, `RATE_LIMITED`, `INTERNAL_ERROR`.

## `DELETE /api/v1/comparisons/{comparison_id}`

Deletes one stored comparison. It does not delete the source documents.

### Request

| Parameter | Required | Meaning |
|---|---:|---|
| `comparison_id` | yes | Unguessable comparison id |

### Example request

```http
DELETE /api/v1/comparisons/cmp_P7nR4tV9xA2mQ6s HTTP/1.1
Host: localhost:8000
```

### Success response

`204 No Content`

### Errors

`COMPARISON_NOT_FOUND`, `RATE_LIMITED`, `INTERNAL_ERROR`.

## `GET /api/v1/capabilities`

Returns `CapabilitiesResponse`: parser capabilities, supported extensions and media types, size limits, and current `DiffOptions` defaults. The client uses this response to build the uploader accept list instead of hardcoding formats. Adding the OCR parser later is therefore a zero-frontend-change event: the server registers a parser, and the accept list changes through this endpoint.

### Request

No parameters.

### Example request

```http
GET /api/v1/capabilities HTTP/1.1
Host: localhost:8000
Accept: application/json
```

### Success response

`200 OK`

```json
{
  "parsers": [
    {
      "parser_name": "PlainTextParser",
      "parser_version": "1.0.0",
      "source_format": "TXT",
      "supported_extensions": [".txt"],
      "supported_media_types": ["text/plain"],
      "capabilities": {
        "preserves_headings": false,
        "preserves_page_numbers": false,
        "is_lossy": false,
        "is_async": false,
        "requires_network": false,
        "emits_confidence": false,
        "emits_bboxes": false
      }
    },
    {
      "parser_name": "MarkdownParser",
      "parser_version": "1.0.0",
      "source_format": "MARKDOWN",
      "supported_extensions": [".md", ".markdown"],
      "supported_media_types": ["text/markdown"],
      "capabilities": {
        "preserves_headings": true,
        "preserves_page_numbers": false,
        "is_lossy": false,
        "is_async": false,
        "requires_network": false,
        "emits_confidence": false,
        "emits_bboxes": false
      }
    },
    {
      "parser_name": "DocxParser",
      "parser_version": "1.0.0",
      "source_format": "DOCX",
      "supported_extensions": [".docx"],
      "supported_media_types": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
      "capabilities": {
        "preserves_headings": true,
        "preserves_page_numbers": false,
        "is_lossy": false,
        "is_async": false,
        "requires_network": false,
        "emits_confidence": false,
        "emits_bboxes": false
      }
    },
    {
      "parser_name": "PdfPlumberParser",
      "parser_version": "1.0.0",
      "source_format": "PDF",
      "supported_extensions": [".pdf"],
      "supported_media_types": ["application/pdf"],
      "capabilities": {
        "preserves_headings": false,
        "preserves_page_numbers": true,
        "is_lossy": true,
        "is_async": false,
        "requires_network": false,
        "emits_confidence": false,
        "emits_bboxes": false
      }
    },
    {
      "parser_name": "PyPdfParser",
      "parser_version": "1.0.0",
      "source_format": "PDF",
      "supported_extensions": [".pdf"],
      "supported_media_types": ["application/pdf"],
      "capabilities": {
        "preserves_headings": false,
        "preserves_page_numbers": true,
        "is_lossy": true,
        "is_async": false,
        "requires_network": false,
        "emits_confidence": false,
        "emits_bboxes": false
      }
    }
  ],
  "max_upload_size_bytes": 26214400,
  "inline_block_budget": 4000,
  "inline_token_budget": 250000,
  "max_blocks_per_comparison": 12000,
  "max_tokens_per_comparison": 750000,
  "default_block_page_limit": 200,
  "max_block_page_limit": 500,
  "diff_options_defaults": {
    "granularity": "WORD",
    "detect_moves": true,
    "align_threshold": 0.5,
    "move_threshold": 0.75,
    "ignore_case": false,
    "ignore_punctuation": false,
    "normalize_whitespace": true
  }
}
```

### Errors

`RATE_LIMITED`, `INTERNAL_ERROR`.

## `GET /api/v1/health`

Reports `HealthResponse` for load balancers and local development.

### Request

No parameters.

### Example request

```http
GET /api/v1/health HTTP/1.1
Host: localhost:8000
Accept: application/json
```

### Success response

`200 OK`

```json
{
  "status": "ok",
  "version": "v1",
  "storage": "ok"
}
```

### Errors

`INTERNAL_ERROR`.

## Error model

Errors use RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail`, and `code`.

```json
{
  "type": "https://palimpsest.app/problems/file-too-large",
  "title": "File too large",
  "status": 413,
  "detail": "The uploaded witness is 31457280 bytes; the maximum is 26214400 bytes.",
  "code": "FILE_TOO_LARGE"
}
```

| Code | Status | When it fires | Client action |
|---|---:|---|---|
| `UNSUPPORTED_FORMAT` | 415 | No registered parser accepts the extension, media type, and magic bytes | Show the supported formats from `/api/v1/capabilities` |
| `FILE_TOO_LARGE` | 413 | The upload exceeds 25 MiB or the request stream crosses the byte limit | Ask the researcher to split or reduce the witness |
| `MALFORMED_DOCUMENT` | 422 | The parser accepts the format but cannot read the bytes as a valid document | Report the parser failure and let the researcher choose another export |
| `EMPTY_DOCUMENT` | 422 | Parsing succeeds but produces no diffable `Block` values | Ask for a witness with extractable text |
| `DOCUMENT_NOT_FOUND` | 404 | The document id is unknown or the row has expired | Re-upload the witness |
| `COMPARISON_NOT_FOUND` | 404 | The comparison id is unknown | Recreate the collation from available witnesses |
| `COMPARISON_EXPIRED` | 410 | The comparison or a referenced document is past `expires_at` | Re-upload and re-run the collation |
| `DIFF_BUDGET_EXCEEDED` | 413 | The requested collation exceeds the absolute token or block budget | Ask the researcher to reduce scope; do not retry automatically |
| `OCR_REQUIRED` | 422 | The upload is an image-only PDF or otherwise needs OCR, which is only a future seam in v1 | State that OCR is required; do not pretend the document is empty |
| `RATE_LIMITED` | 429 | The per-IP token bucket is empty | Retry after the server-provided delay |
| `INTERNAL_ERROR` | 500 | An unexpected server error occurred | Show a generic failure and include the request id in support output |

`OCR_REQUIRED` is a deliberate, honest failure in v1. Returning an empty document for an image-only witness would make the comparison look authoritative while silently omitting the text.

## Limits and safeguards

| Limit or safeguard | v1 value | Reason |
|---|---:|---|
| Maximum upload size | 25 MiB per witness | Keeps parser memory and disk use bounded |
| Inline comparison block budget | 4,000 total blocks | Larger allowed collations move to the `202 ComparisonAccepted` path |
| Absolute comparison block budget | 12,000 total blocks | Protects alignment matrix growth |
| Inline token budget | 250,000 estimated total tokens | Larger allowed collations move to the `202 ComparisonAccepted` path |
| Absolute token budget | 750,000 estimated total tokens | Bounds diff CPU and payload size |
| Maximum block page `limit` | 500 | Keeps virtualized reads responsive |
| Request timeout | 60 seconds for uploads and synchronous diffing | Prevents abandoned requests from occupying workers |
| Rate limiting | Per-IP token bucket, 60 requests per minute with a burst of 20 | A no-auth research tool still needs protection from accidental loops and anonymous abuse |

CORS is restricted to the split development origin and the production frontend origin. In development, the backend allows the configured frontend origin, for example `http://localhost:3000`, and does not allow wildcard credentials.

## OpenAPI

FastAPI generates the machine-readable schema at `/api/v1/openapi.json` with interactive docs at `/docs`. The generated schema is the source of truth for clients and tests; this document is the prose companion. [Testing strategy](./13-testing-strategy.md) requires contract tests that assert the OpenAPI schema and these documented request and response shapes agree.

## Non-goals

There is no auth, no accounts, no webhooks, no GraphQL, and no bulk endpoint surface in v1.
