# ADR-0006 — Export TEI P5 using parallel segmentation

**Status:** Accepted
**Related:** [Overview](../00-overview.md) · [Data schema](../05-data-schema.md) · [API reference](../06-api-reference.md) · [Roadmap](../14-roadmap.md) · [Diff engine](../04-diff-engine.md)

## Context

A comparison currently lives only inside palimpsest: a researcher reads it in the browser, shares an expiring URL, and that is the end of it. [Roadmap](../14-roadmap.md) names TEI XML as the most valuable export for the target audience, because TEI is the interchange format for digital scholarly editions. A collation that cannot leave the tool cannot become part of an edition, be archived, be cited, or be processed by the tooling this audience already runs.

The collation model is already close to what TEI's critical apparatus module describes. `DiffBlock` carries three token streams, block-level status, and group membership; TEI's apparatus carries readings attributed to witnesses. The question is which apparatus method to use and how to encode the structural relations TEI's apparatus module does not model.

## Options considered

### Apparatus method

TEI P5 chapter 12 defines three methods for encoding a critical apparatus.

- **Location-referenced.** The apparatus sits apart from the text and points at it by canonical reference — book, chapter, verse, or page and line. It suits a printed edition being retro-digitised, where the apparatus already exists as a separate footnote apparatus keyed to a reference system. palimpsest has no canonical reference system: its witnesses are arbitrary uploads with no agreed citation scheme, so there is nothing stable to reference.
- **Double-end-point attachment.** Each apparatus entry names the start and end of the lemma it applies to, using anchors embedded in a base text. It handles overlapping and nested variation, which is its real strength. It also requires choosing a base text, and it produces an apparatus whose entries are only interpretable together with the anchors they point at.
- **Parallel segmentation.** The text is divided so that every point of variation becomes an `<app>` containing one `<rdg>` per witness reading, inline, at the position where the variation occurs. Every witness can be reconstructed by selecting its readings and concatenating. Its known limitation is that it cannot represent overlapping variation, because the segmentation must be a single linear partition.

### Structural relations

TEI's apparatus module models *variation in reading*, not *transposition of passages*. It has no `<app>` construct meaning "this paragraph appears elsewhere in the other witness". palimpsest detects `MOVED`, `SPLIT`, and `MERGED`, and those findings are the tool's most distinctive output — discarding them on export would leave the least interesting part of the analysis.

- Invent elements or attributes in the TEI namespace. Produces a file that claims to be TEI and is not valid; hostile to the tooling that is the entire point of exporting.
- Put the relation in `@type` on the block element. Compact, but `<p>` does not carry `@type` in unmodified TEI P5, so this needs an ODD customisation the consumer would have to possess.
- Encode the relations as `<linkGrp>`/`<link>` in `<back>`, pointing at block `@xml:id`s. `<linkGrp>` carries `@type` legitimately, and a link between element identifiers is precisely what a move, split, or merge is.

### Serialisation

`lxml` is faster and supports validation, but adds a compiled dependency for a document that is at most a few megabytes of straightforward markup. Python's standard-library `xml.etree.ElementTree` builds and escapes the same tree with no new dependency and no licence review.

## Decision

Export TEI P5 using **parallel segmentation**, declared in the header as `<variantEncoding method="parallel-segmentation" location="internal"/>`, serialised with the standard library.

Parallel segmentation is the method whose data model matches the one palimpsest already computes. The engine produces, for each block, a linear sequence of runs each attributable to Manuscript A, Manuscript B, or both — which is a parallel segmentation, arrived at independently. The other two methods would require inventing information the tool does not have: a canonical reference system for location-referenced, and a privileged base text for double-end-point attachment. palimpsest deliberately refuses to privilege a base text; `a` and `b` are witnesses, not lemma and variant, and [Overview](../00-overview.md) treats that symmetry as a product commitment rather than an implementation detail.

The overlapping-variation limitation costs nothing here. Overlap cannot arise from this engine: word-level diffing within an aligned pair yields a partition of the block, never overlapping spans.

Structural relations are exported as `<linkGrp type="moved|split|merged">` in `<back>`, with `@target` naming the participating block identifiers. Every block element therefore carries an `@xml:id` derived from `DiffBlock.id`, which also gives citations something stable to point at.

## Consequences

The export is lossy in one direction and honest about it: TEI receives the collation, not the session. Metrics, similarity scores, and `DiffOptions` are recorded as prose in the header rather than as machine-readable fields, because TEI has no vocabulary for them and inventing one would produce markup no consumer understands.

Both witnesses remain reconstructible from the export, which is the property that makes it archival rather than a rendering. This is asserted by tests: selecting every `<rdg wit="#A">` and concatenating must reproduce the Manuscript A pane word for word, and likewise for B. That check is the export's equivalent of the reconstruction invariant in [Data schema](../05-data-schema.md).

Export is a read of an existing comparison, so it inherits session expiry: a TEI file can only be produced while the comparison is alive. That is a deliberate consequence of TTL storage rather than a gap — a researcher who wants a permanent artifact downloads one, and the file is then theirs.

Adding a second export format later must not turn the endpoint into a format switch with divergent semantics. If PDF or HTML export is added, each gets its own path under `/export/`, because a reading artifact and a data artifact have different fidelity obligations.
