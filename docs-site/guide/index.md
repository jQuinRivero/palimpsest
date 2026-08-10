# What palimpsest is

palimpsest compares two versions of a literary text and shows how one witness changes into another. The witnesses are Manuscript A and Manuscript B.

A normal code diff is built for source files: physical lines, monospace text, and dense red/green review. Prose asks different questions. A paragraph may be rewrapped without being rewritten. A passage may move to a new location. A paragraph may split into two with no word edits. Verse may transpose a line while every word stays the same.

palimpsest is built for those cases:

- word-level tokens for insertions, deletions, and unchanged text;
- synoptic and unified views for long-form reading;
- block statuses for `MOVED`, `SPLIT`, and `MERGED` structural change;
- verse compared line by line;
- TEI P5 export using parallel segmentation.

Here is what that buys in one example: one passage moved, one paragraph split
in two, and one word changed from *nothing* to *little*:

```{image} ../_static/synoptic-view.png
:alt: Synoptic view. The summary bar reads "97% similar", "+1 word", "−1 word", "1 block moved, 2 blocks split". Manuscript A and Manuscript B are side by side. "Nothing" is struck through in A and "little" is underlined in B; a panel explains the moved and split passages in words.
:width: 100%
```

A line-oriented diff would report much of the reordering as deleted and
reinserted text. palimpsest keeps the structural findings separate and limits
the wording diff to the one actual revision.

The v1 product boundary is two witnesses at a time, no user accounts, no editing or merging, and no OCR engine. Scanned PDFs are refused honestly with `OCR_REQUIRED` instead of producing an empty comparison.

Normative detail: [overview](https://github.com/jQuinRivero/palimpsest/blob/main/docs/00-overview.md).
