# Quickstart: compare two witnesses

1. Start the API and frontend from [Install and run](install.md).
2. Open <http://localhost:3000>.
3. Upload or paste Manuscript A.
4. Upload or paste Manuscript B.
5. Start the comparison.
6. When the comparison is ready, the app opens `/c/<comparison_id>`.

The comparison URL is shareable until the session expires. The ID is unguessable and expiry is enforced by the SQLite session store.

## What to look for first

- Use **synoptic** view to read Manuscript A and Manuscript B side by side.
- Use **unified** view to read one continuous stream with deletions and insertions inline.
- Use change navigation to jump between modified, inserted, deleted, moved, split, and merged blocks.
- Copy a URL with `?block=<index>` to point a collaborator at a specific block.

If a large comparison is accepted for background processing, the viewer waits for the finished payload rather than pretending a pending result is readable.
