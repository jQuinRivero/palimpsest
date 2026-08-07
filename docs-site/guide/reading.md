# Reading a comparison

## Synoptic and unified views

**Synoptic** view places corresponding material from Manuscript A and Manuscript B in parallel. It is the default close-reading surface.

**Unified** view renders one stream. Deletions remain visible and insertions appear inline, so the earlier reading is still present rather than erased.

```{image} ../_static/unified-view.png
:alt: Unified view of the same comparison, rendering one continuous stream instead of two panes, with the moved and split blocks marked in the margin.
:width: 100%
```

## Word-level tokens

The default granularity is word level. Tokens in the payload are rendered as unchanged, insertion, or deletion. Metrics such as insertions, deletions, and churn are computed by the server and carried in the payload; the browser does not recompute them.

## Structural statuses

`MOVED`
: An aligned block appears out of order. This matters when a passage is transposed without being rewritten.

`SPLIT`
: One Manuscript A block became multiple Manuscript B blocks. A paragraph split can therefore be reported as structure, not as word edits.

`MERGED`
: Multiple Manuscript A blocks became one Manuscript B block.

The **What changed structurally** panel writes those relationships out before
the manuscripts. For example: "Passage 1 in Manuscript A appears as passage 2
in Manuscript B" and "Passage 3 in Manuscript A became passages 3 and 4 in
Manuscript B." The symbols in the gutters then help trace those named passages;
they are not the only explanation.

Verse is segmented as one `VERSE_LINE` block per line, so a transposed line can be reported as `MOVED`. Stanza boundaries are carried separately so a stanza redivision is also visible.

## Navigation and deep links

Change navigation moves among changed blocks: modified, inserted, deleted, moved, split, and merged. The `?block=<index>` query parameter identifies a block ordinal, not a visual line number. Visual lines reflow with viewport width, so they are not stable anchors.

Normative detail: [components](https://github.com/jQuinRivero/palimpsest/blob/main/docs/10-components.md).
