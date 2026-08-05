# ADR-0007 — Carry stanza boundaries through verse segmentation

**Status:** Accepted
**Related:** [Normalization](../03-normalization.md) · [Data schema](../05-data-schema.md) · [API reference](../06-api-reference.md) · [Components](../10-components.md) · [ADR-0006](./0006-tei-parallel-segmentation-export.md)

## Context

Verse is segmented into one `VERSE_LINE` block per line, because the line is the unit a scholar compares: a stanza-sized block reports one revised word as a wholly modified stanza and hides a transposed line entirely.

Segmentation discarded the blank lines between stanzas. Blocks are a flat list, so after segmentation two consecutive stanzas are indistinguishable from one longer one, and the consequence is not cosmetic. Given the same eight lines divided as one block of eight in Manuscript A and as two quatrains in Manuscript B, the collation reports **similarity 1.000, zero edits, and no structural finding of any kind**.

That is a confident wrong answer about exactly the thing the tool claims to show. Dividing an octave into two quatrains is a formal revision; a draft study would care about it as much as about a substituted word. The same comparison reported a `SPLIT` before verse segmentation existed, so this is a capability that was lost rather than one never built.

It also degrades the TEI export. [ADR-0006](./0006-tei-parallel-segmentation-export.md) settled for one `<lg>` per contiguous run of verse lines and recorded the result as "accurate about lines and approximate about stanzas", because the payload carried nothing better.

## Options considered

- **Leave it, and treat stanza division as out of scope.** Cheapest, and defensible if the tool were only about wording. It is not: moved, split and merged passages are the distinctive output, and a stanza break is the same category of finding. It would also mean the summary bar continues to assert that two formally different poems are identical.
- **Stop segmenting, and keep the stanza as the block.** Restores stanza-break detection by giving up line-level alignment — the reason segmentation exists. Trading a transposed line for a stanza break is not a fix, only a different loss.
- **Encode the break as a synthetic block.** A zero-width or marker block between stanzas needs no schema change. It also lies to every consumer that counts blocks, iterates them, or reconstructs text from them, and every one of those would need to learn the exception. Invented structure in the payload is worse than absent structure.
- **Reuse `Block.style`.** No schema change, since `style` is a free-form parser-supplied string. It is documented as diagnostic only and explicitly never drives the diff, so overloading it to carry load-bearing structure would make that statement false and hide the dependency from anyone reading the model.
- **Carry the boundary explicitly in the model.** A schema change, and the only option that keeps line-level alignment, keeps the payload honest, and gives the export and the interface something real to render.

## Decision

Carry stanza boundaries explicitly.

`Block.starts_stanza` records that a block opens a stanza. It is set during verse segmentation, which is the only point where the information exists, and is false everywhere else — a paragraph does not begin a stanza.

`DiffBlock.stanza_boundary` reports what the two witnesses say about the same position, as a closed enum: `SHARED` when both begin a stanza there, `A_ONLY` and `B_ONLY` when only one does, and `NONE` when neither does. It is non-null if and only if the block is a `VERSE_LINE`, following the existing convention of `move_distance` and `group_id`, which are non-null exactly when they mean something.

`A_ONLY` and `B_ONLY` are the finding: a stanza break present in one witness and absent in the other. `DiffMetrics.stanza_breaks_changed` counts them, so the summary bar can report the change even when the block list is windowed.

A boolean on `Block` rather than a stanza ordinal: the comparison only ever asks where stanzas begin, and an ordinal would additionally have to stay meaningful across insertion and deletion, which is a harder promise for no extra benefit.

## Consequences

The golden corpus is regenerated, because `DiffBlock` gains a field. That regeneration is review-gated for exactly this reason, and the diff must be read rather than accepted.

The TEI export becomes exact: `<lg>` now begins at each stanza rather than at each contiguous run of verse, which removes the approximation ADR-0006 had to accept. That ADR is not superseded — its decision about parallel segmentation stands — but its stated limitation no longer applies.

Prose pays a null field on every block. That is the cost of a uniform response shape and is consistent with `move_distance` and `group_id`, which are null on most blocks already.

Revisit if drama arrives. Speaker labels and stage directions divide a scene the way a blank line divides a poem, and if that turns out to want the same mechanism, `starts_stanza` is the wrong name for it and should be generalised through a further record rather than quietly widened.
