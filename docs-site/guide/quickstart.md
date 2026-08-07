# Quickstart: compare two witnesses

1. Start the API and frontend from [Install and run](install.md).
2. Open <http://localhost:3000>.
3. Upload or paste Manuscript A.
4. Upload or paste Manuscript B.
5. Start the comparison.
6. When the comparison is ready, the app opens `/c/<comparison_id>`.

```{image} ../_static/uploader.png
:alt: The uploader, with a drop zone for Manuscript A and one for Manuscript B, a swap control between them, and a line naming the formats this server accepts.
:width: 100%
```

## A worked example

Paste these two witnesses. Nothing is rewritten — the second paragraph has moved to the front, and the last paragraph has been split in two:

Manuscript A:

```text
It was the best of times, it was the worst of times.

It was the age of wisdom, it was the age of foolishness.

We had everything before us. We had nothing before us.
```

Manuscript B:

```text
It was the age of wisdom, it was the age of foolishness.

It was the best of times, it was the worst of times.

We had everything before us.

We had nothing before us.
```

palimpsest reports **100% similar**, **no wording changes**, and **1 block moved, 2 blocks split**. Not one word is marked as inserted or deleted, because not one word was.

The comparison URL is shareable until the session expires. The ID is unguessable and expiry is enforced by the SQLite session store.

## What to look for first

- Use **synoptic** view to read Manuscript A and Manuscript B side by side.
- Use **unified** view to read one continuous stream with deletions and insertions inline.
- Use change navigation to jump between modified, inserted, deleted, moved, split, and merged blocks.
- Copy a URL with `?block=<index>` to point a collaborator at a specific block.

If a large comparison is accepted for background processing, the viewer waits for the finished payload rather than pretending a pending result is readable.
