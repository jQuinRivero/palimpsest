This document defines the v1 session cache: what is stored in SQLite, how rows expire, and why shareable comparison URLs work without accounts.

**Status:** Draft

**Related:** [Spec index](./README.md) · [Architecture](./01-architecture.md) · [API reference](./06-api-reference.md) · [Performance and scale](./11-performance-and-scale.md) · [ADR-0003](./adr/0003-sqlite-session-store.md)

## What we are storing and why it is not a database in the usual sense

Sessions are a cache with a deadline, not a system of record. The researcher's manuscripts are the system of record and they live on the researcher's machine. `palimpsest` stores parsed witnesses and comparison results only so the researcher can read, refresh, and share a collation URL during the cache lifetime.

This framing drives the design. Rows may expire. Migrations may drop incompatible cache content. Logs must never contain document text. The storage layer is optimized for write-once, read-many payloads rather than editorial history, auditability, or long-term preservation.

## Why SQLite over in-process memory

SQLite is specified by [ADR-0003](./adr/0003-sqlite-session-store.md) because it gives v1 the useful persistence of a small database without adding infrastructure. It survives a restart or redeploy in the middle of a reading session. It makes comparison URLs genuinely shareable and citable for the lifetime of the TTL, because another browser can resolve the same id after the original worker process exits. It gives expiration as a simple `DELETE` over `expires_at`, rather than a bespoke in-memory eviction policy. It also keeps local development identical to the smallest production deployment shape.

## The `SessionStore` protocol

The storage boundary is a Python `Protocol` using structural typing. `SqliteSessionStore` is the v1 implementation.

```python
class SessionStore(Protocol):
    def put_document(self, document: Document, *, size_bytes: int, expires_at: datetime) -> DocumentSummary: ...
    def get_document(self, document_id: str) -> Document | None: ...
    def delete_document(self, document_id: str) -> None: ...
    def put_comparison(self, comparison: ComparisonResult, *, status: str, expires_at: datetime) -> ComparisonResult: ...
    def get_comparison(self, comparison_id: str) -> ComparisonResult | None: ...
    def get_comparison_blocks(self, comparison_id: str, offset: int, limit: int) -> BlockPage | None: ...
    def delete_comparison(self, comparison_id: str) -> None: ...
    def sweep_expired(self, now: datetime) -> int: ...
```

The protocol exists precisely because SQLite has a single-writer constraint. Under WAL it supports many concurrent readers, but writes still serialize. That forecloses treating a shared SQLite file as a horizontally scaled write backend, fanning many background workers into independent write transactions, or relying on network filesystems for correctness. Horizontal scaling therefore requires swapping the implementation, not editing the API handlers or diff engine. A Postgres or Redis implementation must satisfy the same method set and preserve the same TTL, expiry, and error semantics.

## Schema

The table and column names match the canonical contract exactly.

```sql
CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  source_format TEXT NOT NULL,
  blocks_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  size_bytes INTEGER NOT NULL
);

CREATE TABLE comparisons (
  id TEXT PRIMARY KEY,
  a_document_id TEXT NOT NULL,
  b_document_id TEXT NOT NULL,
  options_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  blocks_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  status TEXT NOT NULL,
  FOREIGN KEY (a_document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY (b_document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE INDEX idx_documents_expires_at ON documents(expires_at);
CREATE INDEX idx_comparisons_expires_at ON comparisons(expires_at);
CREATE INDEX idx_comparisons_a_document_id ON comparisons(a_document_id);
CREATE INDEX idx_comparisons_b_document_id ON comparisons(b_document_id);
```

| Column | Meaning |
|---|---|
| `documents.id` | Unguessable document id returned by `POST /api/v1/documents` |
| `documents.title` | Researcher-facing witness title |
| `documents.source_format` | `SourceFormat` value selected by the parser registry |
| `documents.blocks_json` | Serialized `list[Block]` from the parsed `Document` |
| `documents.metadata_json` | Serialized `DocumentMetadata` |
| `documents.warnings_json` | Serialized `list[IngestionWarning]` |
| `documents.created_at` | RFC 3339 UTC insertion timestamp |
| `documents.expires_at` | RFC 3339 UTC deadline; read paths must enforce it |
| `documents.size_bytes` | Uploaded byte size for quotas and diagnostics |
| `comparisons.id` | Unguessable comparison id used by `/c/{comparison_id}` |
| `comparisons.a_document_id` | Foreign key to Manuscript A |
| `comparisons.b_document_id` | Foreign key to Manuscript B |
| `comparisons.options_json` | Serialized `DiffOptions` used for the collation |
| `comparisons.metrics_json` | Serialized `DiffMetrics` |
| `comparisons.blocks_json` | Serialized `list[DiffBlock]` |
| `comparisons.created_at` | RFC 3339 UTC creation timestamp |
| `comparisons.expires_at` | RFC 3339 UTC deadline for the comparison |
| `comparisons.status` | Job state used by the `202 Accepted` polling path |
| `schema_migrations.version` | Forward-only migration number |
| `schema_migrations.applied_at` | RFC 3339 UTC timestamp for the migration |

`blocks_json`, `metadata_json`, `warnings_json`, `options_json`, and `metrics_json` are serialized JSON because the payload is written once, read whole, and never queried by content. Normalizing those structures into rows would add join work without improving the v1 access patterns.

The trade-off is `GET /api/v1/comparisons/{comparison_id}/blocks`: windowed block reads must extract a slice from `blocks_json`. The implementation reads the JSON array, returns `blocks[offset:offset + limit]`, defaults `limit` to 200, and keeps it capped at 500. If real workloads show that JSON extraction dominates latency or stored comparisons routinely approach the maximum block count, a normalized `comparison_blocks` table keyed by `comparison_id` and block ordinal becomes worth it.

## Pragmas and connection handling

Each connection applies the required pragmas:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

`journal_mode=WAL` allows readers to continue while a writer commits. `synchronous=NORMAL` is the right durability trade-off for a cache: SQLite still protects database consistency, while avoiding the heaviest fsync path. `foreign_keys=ON` makes document deletion cascade to dependent comparisons. `busy_timeout=5000` gives a writer or reader up to 5000 milliseconds to wait for a transient lock before failing.

The default application shape is connection-per-request, not a large pool. SQLite under WAL is many-reader, single-writer; more write connections do not create more write throughput. Writes must be short: serialize payloads before opening the write transaction, insert or delete, commit, and release the connection.

## Lifecycle and TTL

The default document TTL is 24 hours. The default comparison TTL is 7 days. Both are configurable through application settings because deployment disk budgets differ.

`expires_at` is set at insert time from the server clock. Reads must check `expires_at` before returning content. An expired-but-not-yet-swept row returns `COMPARISON_EXPIRED` for comparison reads and `DOCUMENT_NOT_FOUND` for direct document reads; it must not return stale manuscript text.

TTL does not extend on access. That is deliberate: a shared link should have a predictable end, and passive refreshes from browser tabs or crawlers must not keep unpublished scholarly material alive indefinitely.

The sweeper runs periodically and deletes expired rows:

```sql
DELETE FROM comparisons WHERE expires_at <= :now;
DELETE FROM documents WHERE expires_at <= :now;
PRAGMA optimize;
```

Foreign-key cascade handles the case where a document expires before a comparison that references it: deleting the document deletes the comparison. If a comparison read observes missing or expired source documents before the sweeper runs, it returns `COMPARISON_EXPIRED`.

`PRAGMA optimize` lets SQLite update planner statistics opportunistically. `VACUUM` is not part of the normal sweep because it rewrites the database; run it only during maintenance after large cache churn or after lowering the disk budget.

## Shareable comparison URLs

The frontend route is `/c/{comparison_id}`. The unguessable id is the whole access model: anyone with the link can read the comparison until it expires, and nobody without the link can feasibly discover it by enumeration.

Comparison responses set:

```http
X-Robots-Tag: noindex
Cache-Control: private, no-store
```

These headers prevent unpublished scholarly material from being indexed or cached by an intermediary. They are not authorization. The honest limitation is that anyone with the link has access; the TTL is the mitigation.

## Disk budget and backpressure

A 100k-word manuscript pair can produce roughly 15 MiB to 40 MiB of raw comparison JSON, depending on block count, token churn, and PDF extraction noise. The storage target is a compacted or compressed average footprint near 5 MiB per live reference comparison, matching the 5 GiB default store budget for about 1,000 live comparisons. The v1 maximum total store size is 5 GiB by default and is configurable.

When the store reaches the budget, the server sweeps expired rows aggressively and then rejects new uploads if the budget is still exceeded. It must fail clearly rather than silently thrash the disk or evict live sessions. The API reports this with `INTERNAL_ERROR` and a problem `detail` that says the session store is temporarily over capacity. The diff and block-count budgets are defined with the broader performance model in [Performance and scale](./11-performance-and-scale.md).

## Privacy posture

`palimpsest` collects no PII and performs no analytics on document content. Uploaded text may be unpublished, copyrighted, or sensitive scholarly material, and everything in the session store expires.

Logs may contain request ids, endpoint paths, upload sizes, parser names, durations, response statuses, and error codes. Logs must never contain document text, block text, token text, uploaded filenames with local paths, or serialized JSON payloads from `blocks_json`.

## Migrations

`schema_migrations` records forward-only numbered migrations. Each migration inserts its version and `applied_at` after it succeeds. Migrations are never edited after release; a later migration supersedes an earlier decision.

Because this store is a cache, a breaking schema change may simply drop and recreate the SQLite file after refusing in-flight requests or during startup maintenance. That is a real advantage of not being a system of record: incompatible cache contents can expire or be discarded without data migration promises to researchers.
