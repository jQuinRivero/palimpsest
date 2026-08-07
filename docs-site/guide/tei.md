# TEI P5 export

A finished comparison can be exported as TEI P5:

```text
GET /api/v1/comparisons/{comparison_id}/export/tei
```

The export uses TEI parallel segmentation. Each point of variation becomes an apparatus entry with readings for Manuscript A and Manuscript B. Structural relations that TEI apparatus markup does not model directly, such as moves, splits, and merges, are recorded as `<linkGrp>` entries in the back matter.

The export is available while the comparison session is alive. Once the session expires, the comparison URL and export endpoint expire with it; the downloaded TEI file is the permanent artifact.

Decision record: [ADR-0006](https://github.com/jQuinRivero/palimpsest/blob/main/docs/adr/0006-tei-parallel-segmentation-export.md).
