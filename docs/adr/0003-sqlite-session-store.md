# ADR-0003 — Cache sessions in SQLite with a TTL

**Status:** Accepted
**Related:** [Architecture](../01-architecture.md) · [API reference](../06-api-reference.md) · [Session storage](../07-session-storage.md)

## Context

A comparison must outlive the request that created it. A researcher may read across sessions and share a comparison URL with a colleague. At the same time, witnesses are not ours to keep: they may be unpublished, copyrighted, private, or otherwise unsuitable for indefinite retention.

The storage layer therefore needs durable, shareable, expiring state. It is a cache with a deadline, not a system of record. The researcher's own manuscripts remain the system of record, and this framing is what makes destructive schema migration acceptable.

## Options considered

- An in-process dict or LRU cache. It is the simplest possible implementation, requires no external service, and is easy to test. It fails the product requirement because comparisons disappear on restart or redeploy, and URLs cannot be reliably shared.
- SQLite with `expires_at` and a sweeper. It gives durable local state, simple operational behaviour, transactions, and a trivial expiration query while preserving a single-container deployment.
- Redis. It has excellent TTL semantics and is designed for expiring cache entries. It also adds infrastructure, connection handling, persistence decisions, and deployment requirements that are out of proportion for a greenfield local cache.
- Postgres. It is a strong system of record with robust concurrency and horizontal deployment paths. Those strengths are unnecessary for expiring comparison artefacts and would make the default deployment heavier than the product needs.

## Decision

Cache documents and comparisons in SQLite with `expires_at` columns and a sweeper that removes expired rows.

The store is a deadline-bound cache, not archival storage. The normative schema lives in [Session storage](../07-session-storage.md), and callers interact through the `SessionStore` Protocol rather than directly through SQLite.

## Consequences

This gives durable, shareable, citable URLs without extra infrastructure. Expiration is operationally simple: `DELETE ... WHERE expires_at < now()` removes data the application no longer has a reason to keep.

The cost is concurrency and scale. SQLite under WAL permits one writer, so this process does not scale horizontally as-is. That is why [Session storage](../07-session-storage.md) specifies a `SessionStore` Protocol: a networked implementation can replace SQLite without changing ingestion, diffing, API, or frontend callers.

Unguided sharing also means unguessable IDs are the entire access-control model. Comparison and document IDs must contain at least 128 bits of entropy, and comparison responses must set `X-Robots-Tag: noindex` and `Cache-Control: private, no-store`. Revisit this decision if multi-instance writes become required, if retention policy changes from cache to archive, or if access control expands beyond possession of an unguessable URL.
