This document specifies the React component contract for uploading witnesses and reading a finished `ComparisonResult`.

**Status:** Implemented and normative for v1

**Related:** [README](./README.md) · [Data schema](./05-data-schema.md) · [API reference](./06-api-reference.md) · [Frontend architecture](./08-frontend-architecture.md) · [Design system](./09-design-system.md) · [Performance and scale](./11-performance-and-scale.md)

The client does not compute a diff. It uploads two witnesses, asks the backend for a `ComparisonResult`, and renders the returned `DiffBlock` and `Token` data without inventing client-only statuses.

## Component tree

```text
/
└─ ManuscriptUploader
   ├─ EmptyState
   └─ per-witness controls for Manuscript A and Manuscript B

/c/[comparisonId]
└─ DiffViewer
   ├─ DiffSummaryBar
   ├─ StructuralSummary                explicit moved/split/merged sentences
   ├─ SourceOrderOverview              each witness in its original sequence
   ├─ ViewModeToggle
   ├─ ChangeNavigator
   ├─ LoadingProgress                  while a windowed comparison loads
   ├─ VirtualizedSynopticView          when ViewMode is SYNOPTIC
   │  ├─ DiffBlockRow                  Manuscript A pane
   │  │  ├─ ChangeGutter
   │  │  └─ TokenSpan
   │  ├─ BlockConnector
   │  └─ DiffBlockRow                  Manuscript B pane
   │     ├─ ChangeGutter
   │     └─ TokenSpan
   └─ VirtualizedUnifiedView           when ViewMode is UNIFIED
      └─ DiffBlockRow
         ├─ ChangeGutter
         └─ TokenSpan
```

The gutter shows block ordinals from `a_index` and `b_index`. These are not rendered visual line numbers. Prose reflows with viewport width, so visual line numbers are not stable anchors.

## Shared conventions

| Convention | Requirement |
|---|---|
| Client boundary | `ManuscriptUploader`, `DiffViewer`, `VirtualizedSynopticView`, `VirtualizedUnifiedView`, `DiffSummaryBar`, `StructuralSummary`, `SourceOrderOverview`, `DiffBlockRow`, `TokenSpan`, `ChangeGutter`, `ChangeNavigator`, `LoadingProgress`, `ComparisonPending`, `ViewModeToggle`, `BlockConnector`, and `EmptyState` render inside client boundaries because they consume browser state or the interactive comparison payload. |
| Naming | Public props use `comparisonId`, `comparison`, `blocks`, `metrics`, `options`, `a`, `b`, `a_index`, and `b_index` only where those names mirror the contract. UI text always says Manuscript A and Manuscript B, never positional pane labels. |
| Memoization | `TokenSpan` is memoized by `text`, `status`, and announcement mode. `DiffBlockRow` is memoized by `DiffBlock.id`, pane, expansion state, and focus state. Handlers passed into virtualized rows are stable callbacks. |
| DOM discipline | A 100,000-word manuscript can produce about 120,000 word tokens per witness before payload run-coalescing. A payload `Token` is a contiguous run, not necessarily one word. Rows render only the current virtual window and must never compute metrics by counting `Token` array entries. |
| URL state | `?view=synoptic` maps to `ViewMode.SYNOPTIC`; `?view=unified` maps to `ViewMode.UNIFIED`. `?block=<index>` uses the block ordinal, not a DOM row number. `?moves=on|off` controls whether move connectors are shown; it does not mutate `DiffOptions.detect_moves`, which only records how the backend computed the payload. |
| Testability hooks | Components expose stable `data-testid` values for the component root and block ids: `manuscript-uploader`, `diff-viewer`, `synoptic-view`, `diff-summary-bar`, `structural-summary`, `source-order-overview`, `source-order-a-{index}`, `source-order-b-{index}`, `block-loading-status`, `diff-block-row-{id}`, and `token-{status}`. Hooks must not encode rendered pixel position. |

## ManuscriptUploader

`ManuscriptUploader` collects two witnesses, validates them against server-advertised parser capabilities, uploads each witness with progress, and starts a comparison.

### Props

```ts
export interface ManuscriptUploaderProps {
  initialOptions?: Partial<DiffOptions>;
  onComparisonCreated?: (comparison: ComparisonResult) => void;
  onAccepted?: (accepted: ComparisonAccepted) => void;
  onError?: (problem: ApiProblem) => void;
}
```

`ComparisonAccepted` and `ApiProblem` are API response types matching [API reference](./06-api-reference.md). They are named in frontend code but serialized from the backend response. `ComparisonAccepted` is imported from `lib/types.ts`, which derives it from the OpenAPI schema; it must never be re-declared by hand, because a hand-written copy can disagree with the server and nothing will catch it.

### Internal state

| State | Shape | Purpose |
|---|---|---|
| Capabilities | `CapabilitiesResponse | null` | Source of truth for accepted extensions, media types, and size limits fetched from `GET /api/v1/capabilities`. Accept lists are never hardcoded in the component. |
| Witness slot | `{ label: "Manuscript A" \| "Manuscript B"; state: SlotState; file?: File; document?: DocumentSummary; warnings: IngestionWarning[]; progress: number; error?: ApiProblem }` | Tracks each witness independently. |
| Paste draft | `{ aText: string; bText: string }` | Holds pasted text before it is converted to a `TXT` upload. |
| Options | `DiffOptions` | Defaults to `granularity: WORD`, `detect_moves: true`, `align_threshold: 0.50`, `move_threshold: 0.75`, `ignore_case: false`, `ignore_punctuation: false`, `normalize_whitespace: true`. |
| Submission | `{ isSubmitting: boolean; problem?: ApiProblem }` | Prevents duplicate comparison creation and surfaces final errors. |

```ts
export type SlotState = "empty" | "selected" | "uploading" | "uploaded" | "error";
```

### Behaviour

Each witness has a drop zone labelled Manuscript A or Manuscript B. The drop zone supports drag-and-drop, click-to-browse, and paste-text. Pasted text is treated as a `TXT` witness with a generated title; the user still sees it as Manuscript A or Manuscript B.

Validation before upload is a courtesy, not a gate. The server re-checks format and size on every upload and is the sole authority on both; the client checks early only so nobody waits on a request that cannot succeed.

1. Fetch `GET /api/v1/capabilities`.
2. When capabilities are available, compare the candidate extension, media type, and size to the returned accept list and limits.
3. If the candidate is too large, keep the slot in `selected` or `error` and show size-limit feedback before any network request.
4. When capabilities have **not** arrived yet, upload anyway and let the server answer. The component must not refuse a file for a rule it has not been told. Refusing with `UNSUPPORTED_FORMAT` in this window is specifically forbidden: nothing has inspected the file, the claim may be false, and discarding the selection forces the researcher to choose it again. A drop is reachable in this window even though the file input and browse button are disabled, because `onDrop` is not gated.
5. If the candidate is a format that requires OCR, display the `OCR_REQUIRED` problem as: "This witness appears to require OCR before it can be compared. Export searchable text, upload a text-based PDF, or enable the OCR parser when it becomes available."
6. Upload accepted witnesses to `POST /api/v1/documents`, one per slot, showing per-file progress.
7. Render any `IngestionWarning` values returned on the `DocumentSummary` under the relevant witness.
8. Enable the compare action only when both slots are `uploaded`.
9. Submit `{a_document_id, b_document_id, options?}` to `POST /api/v1/comparisons`.
10. On `201 ComparisonResult`, route to `/c/[comparisonId]`, concretely `/c/<comparison.comparison_id>`, and optionally call `onComparisonCreated`.
11. On `202 ComparisonAccepted`, call `onAccepted`, wait for the collation to finish, then route to `/c/[comparisonId]`, concretely `/c/<comparison_id>`. `comparison_id` is always present on a `202`; it is required by the schema, so no branch may treat it as optional.

Because either authority may refuse, and which one does is a race whenever capabilities are slow, a refusal must read the same either way. The server's message is about parsers rather than about this upload and names no file, so the component supplies the filename itself rather than relying on the message to carry it.

### Accepted formats copy

The sentence naming accepted formats is prose written for a researcher, derived from `GET /api/v1/capabilities` and never hardcoded. It must not render the `accept` attribute, which is a comma-joined list of extensions and media types built for the file picker and unreadable as text. Formats are named once each even when several parsers read the same one, and a format with no human label falls back to its extensions so that registering a new parser needs no change here. No other part of the component may state its own list of formats.

The swap affordance exchanges the two slots before comparison creation. It must swap selected files, uploaded `DocumentSummary` values, warnings, progress, and errors together so Manuscript A and Manuscript B remain semantically correct.

### Accessibility

| Element | Requirement |
|---|---|
| Drop zones | Keyboard-focusable buttons or labelled regions with clear names: "Upload Manuscript A" and "Upload Manuscript B". |
| Progress | Per-witness progress uses `role="progressbar"` with `aria-valuenow`, `aria-valuemin="0"`, and `aria-valuemax="100"`. |
| Warnings | `IngestionWarning` lists are associated with the witness via `aria-describedby`. |
| Errors | Problem details are announced in a polite live region; `OCR_REQUIRED` uses the specific message above. The announcement is self-contained: it names the witness and the file, because a listener has only that sentence while a reader also has the card. |
| Swap | The swap control is a button labelled "Swap Manuscript A and Manuscript B". |

### Edge, empty, and error states

| State | Rendering |
|---|---|
| No capabilities yet | Disable the file input, browse, and paste controls, show a loading message, and do not guess accepted formats. A file dropped in this window is still uploaded and answered by the server; it is never refused locally. |
| `empty` | Show `EmptyState` with upload and paste guidance. |
| `selected` | Show title, size, detected type if available, and a replace action. |
| `uploading` | Disable replacement for that witness, show progress, and allow cancelling the upload. |
| `uploaded` | Show `DocumentSummary.metadata.word_count`, `DocumentSummary.metadata.block_count`, parser name, and warnings. |
| `error` | Show the RFC 9457 `title`, `detail`, and `code`, plus the filename, with `OCR_REQUIRED` handled specifically. |

### Design tokens consumed

`ManuscriptUploader` consumes `--color-ink`, `--color-ink-muted`, `--color-paper`, `--color-vellum`, `--color-rule`, `--color-rubric`, `--font-ui`, `--font-manuscript`, and `--font-mono`.

## DiffViewer

`DiffViewer` owns view state for a loaded `ComparisonResult` and chooses between synoptic and unified rendering.

### Props

```ts
export interface DiffViewerProps {
  comparison: ComparisonResult;
  initialMode?: ViewMode;
  /** Seeded from the server so a shared ?block= link paints correctly and both
   *  renders agree. Bounded by `total_blocks`, not by the loaded window. */
  initialBlockIndex?: number | null;
}
```

`DiffViewer` is keyed by `comparison.comparison_id` at the route, so moving between comparisons builds a fresh viewer rather than carrying one comparison's loaded blocks into another.

### Internal state

| State | Purpose |
|---|---|
| `viewMode: ViewMode` | Mirrors `?view=synoptic\|unified`, defaulting to `ViewMode.SYNOPTIC`. |
| `movesEnabled: boolean` | Mirrors `?moves=on\|off`, defaulting from `comparison.options.detect_moves`. |
| `activeBlockIndex: number \| null` | Mirrors `?block=<index>` and drives focus and scroll. Bounded by `total_blocks` for intent and by loaded blocks for rendering, so a citation into an unloaded window waits rather than being discarded. |
| `blocks: DiffBlock[]` | `comparison.blocks` when `truncated` is `false`; otherwise grows window by window from `GET /api/v1/comparisons/{comparison_id}/blocks?offset=&limit=` until it reaches `total_blocks`. Owned by `useWindowedBlocks`. |

### Behaviour

`DiffViewer` reads URL state on mount and writes it with replacement navigation so view changes do not pollute history. Unknown `?view=` values fall back to `synoptic`. Unknown `?moves=` values fall back to `on` when `comparison.options.detect_moves` is `true`.

Keyboard navigation moves between changed blocks: `BlockStatus.MODIFIED`, `BlockStatus.INSERTED`, `BlockStatus.DELETED`, `BlockStatus.MOVED`, `BlockStatus.SPLIT`, and `BlockStatus.MERGED`. Next and previous change commands update `?block=<index>`, focus the target row, and ask the virtualizer to scroll the block into view. The request must go through the virtualizer rather than the DOM, because a row outside the rendered window does not exist to be scrolled to.

Scroll-to-block may be smooth only when `prefers-reduced-motion` is not `reduce`; otherwise the component must jump immediately and preserve focus without animation.

When `comparison.truncated` is `true`, the component treats `comparison.blocks` as the initial window only, uses `comparison.total_blocks` as the authoritative count, and loads the remaining windows through `GET /api/v1/comparisons/{comparison_id}/blocks?offset=&limit=` until the collation is whole. See [Frontend architecture](./08-frontend-architecture.md) for why every window is loaded rather than only those approached by scrolling, and [Performance and scale](./11-performance-and-scale.md) for when the server windows a comparison at all.

Rendering a window as though it were the whole collation is prohibited. While loading, the viewer must:

| Requirement | Reason |
|---|---|
| State how many blocks of how many have loaded | A reader drawing conclusions about a text needs to know whether they are looking at all of it. `LoadingProgress` owns this, in a polite live region. |
| Mark counts derived from loaded blocks as provisional | The change count grows as windows arrive. `ChangeNavigator` takes `partial` and renders "so far", because a number that will change must not read as a finding. |
| Keep `?block=` even when its target is unloaded | Stripping it is how a shared citation into a long manuscript silently becomes a link to the top of the document. |
| Report a failed window honestly, with a retry | A comparison that stopped loading part-way is incomplete, and saying nothing would leave the reader with a plausible-looking fragment. |

Metrics in `DiffSummaryBar` always describe the whole comparison, because the server computes them over the whole comparison. That mismatch with a partially loaded block list is precisely why the loading state has to be visible.

### Synoptic rendering

Synoptic view renders two columns labelled Manuscript A and Manuscript B inside `VirtualizedSynopticView`. It is one `react-virtuoso` list whose rows are three-cell grids, not two virtualized panes. A single `DiffBlock` is rendered across both columns of one row:

| `BlockStatus` | Manuscript A pane | Manuscript B pane | Row correspondence |
|---|---|---|---|
| `UNCHANGED` | `a_tokens` | `b_tokens` | Natural 1:1 aligned pair. |
| `MODIFIED` | `a_tokens` with `DELETION` spans | `b_tokens` with `INSERTION` spans | The taller pane determines the shared row height. |
| `DELETED` | Content from `a_tokens` | Held-open gap or collapsed marker | The gap preserves the reading line across panes. |
| `INSERTED` | Held-open gap or collapsed marker | Content from `b_tokens` | The gap preserves the reading line across panes. |
| `MOVED` | Content where the block occurs in Manuscript A | Content where the aligned block occurs in Manuscript B | `BlockConnector` shows non-monotonic correspondence; the shared grid row keeps the pair aligned. |
| `SPLIT` | Source block member of `group_id` | Multiple target blocks sharing `group_id` | The group is measured as a composite anchor. |
| `MERGED` | Multiple source blocks sharing `group_id` | Target block member of `group_id` | The group is measured as a composite anchor. |

Correspondent row heights are maintained by measuring both rendered row elements. If Manuscript A is taller, Manuscript B receives a held-open spacer for that `DiffBlock`; if Manuscript B is taller, Manuscript A receives the spacer. The spacer is semantic layout only and is hidden from the accessibility tree.

### Unified rendering

Unified view renders one column at `--measure-prose` inside `VirtualizedUnifiedView`. It uses `DiffBlock.tokens` as the authoritative inline stream. `TokenStatus.DELETION` tokens are shown through rather than removed, so the prior reading remains visible. `TokenStatus.INSERTION` tokens remain inline at their returned location. `ChangeGutter` still shows the block ordinal; when both `a_index` and `b_index` exist, it exposes both in the label.

Unified is virtualized on the same terms as synoptic. It was not, originally, and rendered one row per block: acceptable while the client only ever held the server's first window, and not once it began loading the whole comparison. Measured at 300 blocks, it mounted 300 rows against the budget of about 120 in [Performance and scale](./11-performance-and-scale.md), scaling with the manuscript and bounded by nothing.

Both reading surfaces therefore expose the same `BlockListHandle`, which is what allows navigation to scroll to a block without knowing which view is mounted.

### Accessibility

`DiffViewer` exposes a named region for the comparison and a second named region for the summary. Pane labels are Manuscript A and Manuscript B. Keyboard navigation announces the target block status and ordinal without reading the whole block automatically.

### Edge, empty, and error states

| State | Rendering |
|---|---|
| `comparison.blocks.length === 0` and `comparison.total_blocks === 0` | `EmptyState` explaining that both witnesses normalized to no comparable blocks. |
| Expired comparison | Show the `COMPARISON_EXPIRED` problem and a link back to `/`. |
| Missing page while windowed | Keep the current window visible, show a retry affordance, and do not clear loaded blocks. |
| `?block=` outside `total_blocks` | Remove the parameter and keep the current view. |

### Design tokens consumed

`DiffViewer` consumes `--color-ink`, `--color-ink-muted`, `--color-paper`, `--color-vellum`, `--color-rule`, `--font-ui`, `--font-manuscript`, `--measure-prose`, and `--leading-manuscript`.

## VirtualizedSynopticView

`VirtualizedSynopticView` renders synoptic view. It is **one** `react-virtuoso` list, not two: each row is a three-cell grid holding the Manuscript A cell, the `BlockConnector`, and the Manuscript B cell for a single `DiffBlock`. Corresponding blocks therefore share a row and are aligned by layout, which is why no scroll synchronization exists to go wrong. See [SyncScrollContainer](#syncscrollcontainer) for the design this replaced and why.

### Props and handle

Both reading surfaces implement the shared `BlockListHandle` from `components/blockList.ts`, so navigation can scroll to a block without knowing which view is mounted.

```ts
export interface BlockListHandle {
  scrollToBlock: (index: number) => void;
}

// Props, identical for VirtualizedSynopticView and VirtualizedUnifiedView
{
  blocks: DiffBlock[];
  showStructuralMarkers: boolean;
  height?: string;         // default "70vh"
  renderAll?: boolean;     // suspend virtualization; see doc 09 on printing
}
```

Navigation must go through `scrollToBlock` rather than querying the DOM: a row outside the rendered window has no element to scroll to, so a DOM-based jump silently fails on exactly the long manuscripts virtualization exists for.

### Requirements

| Concern | Requirement |
|---|---|
| Row identity | Rows are keyed by `DiffBlock.id`, never by array position, so a window replacement cannot recycle a mounted row into a different block. |
| Height | Row height is the taller of the two cells, so the two witnesses start on the same baseline. |
| Held-open gaps | `INSERTED` and `DELETED` render an empty cell on the absent side rather than collapsing the row, preserving the reading line across the grid. |
| Overscan | Expressed in pixels through `increaseViewportBy`, because that is the unit Virtuoso offers and prose block heights are not known in advance. The default is 1200px, roughly a viewport of prose above and below. |
| Pane headings | Rendered as real headings outside the scroller, so they remain visible while rows move beneath them and are reachable by assistive technology rather than read as decorative column labels. |
| Reduced motion | `scrollToBlock` uses `behavior: "auto"`, so jumps are always immediate and `prefers-reduced-motion` needs no special case. |
| Single-column fallback | Below the `md` breakpoint the grid collapses to one column and the connector is hidden; there is no viewport at which two prose columns are legible on a phone. |
| Printing | `renderAll` mounts every row. Only for printing: leaving it on would defeat the point of the component. |

### Design tokens consumed

`VirtualizedSynopticView` consumes `--color-rule`, `--color-vellum`, `--color-moved`, `--color-moved-underlay`, `--font-ui`, and `--leading-manuscript`.

## VirtualizedUnifiedView

`VirtualizedUnifiedView` renders unified view: one `react-virtuoso` list of `DiffBlockRow` in `unified` mode, at `--measure-prose`. It shares `BlockListHandle`, the overscan constant, and the `renderAll` print behaviour with `VirtualizedSynopticView`; only the row renderer differs.

Both views must stay within the mounted-row budget in [Performance and scale](./11-performance-and-scale.md) at any manuscript length. That is a property of the component, not of the payload: the client loads every block of a windowed comparison, so nothing upstream limits how many rows a naive view would mount.

## ComparisonPending

`ComparisonPending` is the waiting page for a comparison the server has accepted but not finished.

It exists because the comparison URL is the shareable artifact. The uploader waits before navigating, but a colleague opening the link — or the researcher refreshing it — reaches `/c/[comparisonId]` directly while the collation is still running. Rendering a comparison that has no blocks yet is how that path returned a `500`.

### Props

```ts
export interface ComparisonPendingProps {
  comparisonId: string;
  retryAfter: number;   // seconds, from the server's ComparisonAccepted
}
```

### Requirements

| Concern | Requirement |
|---|---|
| Copy | States that the collation is running and that the link keeps working. It must not estimate a completion time: the server does not predict one, so the interface would be inventing it. |
| Polling | Delegates to `waitForComparison` — bounded exponential backoff with full jitter, seeded from `retry_after`. Aborts on unmount. |
| Arrival | Calls `router.refresh()` rather than reloading, so the server component re-runs and renders the finished comparison in place. |
| Failure | A terminal error is shown, not swallowed. Polling past a comparison the server has given up on would leave the reader watching a spinner indefinitely. |
| Announcement | The waiting copy sits in a polite live region; the failure message is an alert. |

## LoadingProgress

`LoadingProgress` reports how much of a windowed comparison has arrived. It renders nothing visible once the collation is whole, and it is the only place the viewer admits to being incomplete — so its absence when blocks are still loading is a defect, not a cosmetic omission.

### Props

```ts
export interface LoadingProgressProps {
  loadedBlocks: number;
  totalBlocks: number;
  isComplete: boolean;
  error: string | null;
  onRetry: () => void;
}
```

### Requirements

| State | Rendering |
|---|---|
| Loading | Visible, `data-state="loading"`, in an `aria-live="polite"` region. States loaded and total, and warns that metrics describe the whole comparison while navigation reaches only what has loaded. |
| Complete | Visually hidden, `data-state="complete"`, announced once so a screen-reader user learns the earlier provisional counts can now be trusted. |
| Failed | `role="alert"`, `data-state="error"`, stating how many of how many blocks loaded, and offering a retry that resumes from the last successful offset rather than restarting. |

Not shown at all when `comparison.truncated` is `false`, which is the ordinary case; a short comparison must not acquire loading chrome it never needs.

## SyncScrollContainer

> **Superseded by `VirtualizedSynopticView`.** Implementation showed that the
> problem this component was designed to solve can be removed rather than
> solved. A single virtualized list whose rows each contain Manuscript A, the
> connector and Manuscript B places corresponding blocks in one grid row, so
> they are adjacent *by construction* and cannot drift by any amount, at any
> scroll position, under any difference in rendered height. There is one scroll
> position because there is one scroller, and the two-phase measurement dance
> below — approximate `scrollToIndex`, then a corrective frame once the twin
> row's real height is known — becomes unnecessary.
>
> The cost is genuine and is not a degraded version of the design below: the
> panes cannot be scrolled independently, so a researcher cannot hold chapter
> two beside chapter nine. That is a distinct feature and would need a
> deliberate second view; it is recorded in [Roadmap](./14-roadmap.md).
>
> The specification below is retained because it remains the correct design for
> any future independent-pane view, where anchor-linking really is required.

`SyncScrollContainer` synchronizes Manuscript A and Manuscript B in synoptic view. It is anchor-linked to aligned block pairs and never pixel- or percentage-linked across the full scroll range.

### Props

```ts
export interface SyncScrollContainerProps {
  blocks: DiffBlock[];
  total_blocks: number;
  activeBlockIndex?: number | null;
  overscanBlockCount?: number;
  isLocked?: boolean;
  onLockChange?: (isLocked: boolean) => void;
  onActiveBlockChange?: (blockIndex: number) => void;
  onWindowRequested?: (offset: number, limit: number) => Promise<BlockPage>;
  renderPaneRow: (block: DiffBlock, pane: "A" | "B") => React.ReactNode;
  renderConnector?: (block: DiffBlock) => React.ReactNode;
}
```

### Internal state

| State | Purpose |
|---|---|
| `driverPane: "A" \| "B" \| null` | Last-interacted pane. Wheel, touch, keyboard, scrollbar, and programmatic focus can set it. |
| `syncLock: boolean` | Prevents feedback oscillation while the follower pane is being positioned. |
| `isUnlocked: boolean` | Internal mirror of the `isLocked` prop when uncontrolled. Escape hatch that lets panes scroll independently. |
| `measurements` | Per-pane map of `DiffBlock.id` to top, height, and measured status from `react-virtuoso` and `ResizeObserver`. |
| `anchorIndex` | Leading visible aligned block or group in the driving pane. |
| `pendingFrame` | `requestAnimationFrame` id for batched synchronization. |
| `unmeasuredQueue` | Blocks whose counterpart must be mounted and measured before precise synchronization can complete. |

### Anchor-based algorithm

On every driving scroll event, synchronization runs in `requestAnimationFrame`:

1. Identify the leading visible anchor in the driving pane. The anchor is the first visible `DiffBlock` or `group_id` whose visible top is at or above the pane top and whose bottom is below it.
2. Compute fractional progress within that anchor: `(scrollTop - anchorTop) / anchorHeight`, clamped to `[0, 1]`.
3. Resolve the follower anchor:
   - For `UNCHANGED`, `MODIFIED`, and clean `MOVED` pairs, use the same `DiffBlock.id`.
   - For `SPLIT` and `MERGED`, use the whole `group_id` as a composite anchor and compute progress through the group height.
   - For `INSERTED` and `DELETED`, which have no counterpart, interpolate between the nearest preceding and following anchors that exist in both panes.
4. If the follower anchor is measured, set follower `scrollTop` so the follower anchor top minus the corresponding fractional offset aligns with the pane top.
5. If the follower anchor is not measured, call the `react-virtuoso` imperative handle with `scrollToIndex` for the estimated block index, allow the row to mount, capture its height through `ResizeObserver`, and then run one corrective synchronization frame.

The unmeasured-height problem is expected, not exceptional. A virtualized follower pane often has no DOM element for the twin block exactly when the driver reaches a distant jump. The container resolves this by separating positioning into two phases: first an approximate `scrollToIndex` that forces the target row or group into the rendered range, then a measured correction after `react-virtuoso` reports the actual row height. The user must never see a permanent drift; a one-frame correction is acceptable.

### Driver selection and oscillation control

The last pane to receive direct user input drives. While follower positioning is in progress, `syncLock` ignores scroll events emitted by the follower. The lock clears in the next animation frame after the follower settles. Programmatic navigation to `?block=` temporarily sets the driver to the pane with the concrete block content; for `INSERTED`, Manuscript B drives, and for `DELETED`, Manuscript A drives.

### Complex alignment

| Case | Synchronization rule |
|---|---|
| `MOVED` | Use the aligned pair as the anchor but draw `BlockConnector` to show the non-monotonic relation. If following the move would cause a disorienting jump during ordinary reading, prefer the nearest monotonic bounding anchors until the user focuses the moved block directly. |
| `SPLIT` | Treat all blocks with the same `group_id` as one composite anchor. Fractional progress is computed over the combined measured height. |
| `MERGED` | Same as `SPLIT`, with the composite anchor on the opposite side. |
| `INSERTED` | No Manuscript A counterpart. Interpolate between nearest bounding anchors; if there is no preceding anchor, use the following anchor; if there is no following anchor, use the preceding anchor. |
| `DELETED` | No Manuscript B counterpart. Interpolate using the same bounding-anchor rule. |

### Interaction with `react-virtuoso`

`react-virtuoso` 4.18.11 is required because it provides automatic variable-height measurement through `ResizeObserver` and an imperative handle. `SyncScrollContainer` uses `scrollToIndex` for jumps, reads rendered range callbacks to know what is mounted, and avoids direct DOM queries except for row measurements exposed through row refs.

Overscan is expressed in blocks, not pixels. The default is enough to include the next likely anchor above and below the viewport. When synchronization requests an unmeasured anchor outside overscan, the container requests a block page if needed, then forces the virtualizer to mount the anchor before applying the measured correction.

### Escape hatch

The component exposes a visible "Unlock panes" control and accepts `isLocked`. When unlocked, both panes retain their current positions, driver selection stops, and `BlockConnector` remains visible for orientation. Re-locking uses the active or leading visible block as the new anchor rather than snapping to the prior synchronized position.

### Accessibility

The lock control is a toggle button with `aria-pressed`. Synchronization itself must not steal focus. Pane labels remain Manuscript A and Manuscript B.

### Edge, empty, and error states

| State | Rendering |
|---|---|
| No measured anchors | Keep panes independently scrollable and show a non-blocking "Synchronizing after measurement" status. |
| Windowed target not loaded | Request the needed `BlockPage`; until it arrives, use nearest loaded bounding anchors. |
| Measurement changes after images or fonts settle | Re-run anchor synchronization from the current driver in the next animation frame. |

### Design tokens consumed

`SyncScrollContainer` consumes `--color-rule`, `--color-vellum`, `--color-moved`, `--color-moved-underlay`, `--font-ui`, and `--leading-manuscript`.

## DiffSummaryBar

`DiffSummaryBar` is persistent chrome for `DiffMetrics` and comparison navigation.

Structural findings — moved, split, merged, and changed stanza breaks — are reported separately from wording and are never folded into the edit count. A comparison can honestly read "No wording changes" and still report structural change; a re-paragraphed chapter and a re-divided poem are both exactly that case, and suppressing the second reading would make the bar assert that nothing happened.

### Props

```ts
export interface DiffSummaryBarProps {
  metrics: DiffMetrics;
}
```

### Internal state

None. Every displayed value is derived directly from `DiffMetrics`.

### Behaviour

The bar renders rounded `DiffMetrics.similarity`, wording changes as insertion/deletion word counts (or "No wording changes"), structural counts, and the A-to-B word-count transition. Counts use locale-aware grouping.

`insertions`, `deletions`, `edit_count`, and `unchanged_tokens` are word counts supplied by `DiffMetrics`, never counts derived from `Token[]` length. The bar must not derive textual metrics from rendered tokens.

### Accessibility

Metrics are grouped in a region labelled "Comparison summary". Wording and structural findings are separate phrases so "No wording changes" never implies "nothing changed".

### Edge, empty, and error states

| State | Rendering |
|---|---|
| All wording unchanged | Show "No wording changes"; retain any structural counts. |
| No structural findings | Omit the structural-count phrase. |
| No shared wording | Show `0% similar` and the insertion/deletion word counts. |

### Design tokens consumed

`DiffSummaryBar` consumes `--color-ink`, `--color-ink-muted`, `--color-paper`, `--color-rule`, `--color-rubric`, `--color-addition`, `--color-deletion`, `--color-moved`, `--font-ui`, and `--font-mono`.

## StructuralSummary

`StructuralSummary` translates `MOVED`, `SPLIT`, and `MERGED` payload
relationships into sentences before the manuscript begins. Connectors and
gutter glyphs remain useful for tracing the rows visually, but they are not
treated as a vocabulary a first-time reader should already know.

Examples:

- "Moved — passage 1 in Manuscript A appears as passage 2 in Manuscript B."
- "Split — passage 3 in Manuscript A became passages 3 and 4 in Manuscript B."
- "Merged — passages 3 and 4 in Manuscript A became passage 3 in Manuscript B."

The component groups split and merged members by `group_id`, renders at most
five relationships, and directs the reader to change navigation for the
remainder. It renders only after every block has loaded: describing a partial
split group as one-to-one while its second member is outside the current
window would be a plausible lie.

The structural-marker toggle hides this summary together with the gutter and
connector affordances. Each sentence carries a visible text badge (`Moved`,
`Split`, or `Merged`), so the explanation does not depend on colour or a
special glyph. In synoptic view, each connector repeats the relationship at
the point of reading: `Moved down · A 1 → B 2`, `Split · A 3 → B 4`, or the
corresponding merge. The explicit ordinals are required because aligning the
same prose on one visual row otherwise conceals the movement it is meant to
show.

## SourceOrderOverview

`SourceOrderOverview` preserves the source sequence that the detailed synoptic
reading necessarily rearranges. It reconstructs each original passage from
the side-specific token streams, groups split or merged chunks by their
original index, sorts by `a_index` or `b_index`, and displays both witness
orders before aligned reading begins.

For the worked example, Manuscript A visibly reads `best → age → combined`
while Manuscript B reads `age → best → first half → second half`. Structural
items carry compact labels such as `Moved to B 2` and `Split into B 3, 4`.

When a witness has at most twelve passages, the whole source order is shown.
For larger manuscripts, only structurally changed passages are listed; the
detailed virtualized reading remains the place to read the complete text.
Like `StructuralSummary`, the component waits for all blocks to load and is
hidden by the structural-marker toggle.

## DiffBlockRow

`DiffBlockRow` renders one `DiffBlock` for one pane or for unified view.

A `VERSE_LINE` row reads `stanza_boundary` for two purposes: any non-`NONE` value opens a stanza and takes back the blank line segmentation removed, and `A_ONLY` or `B_ONLY` additionally marks a break the two witnesses disagree about. The second is load-bearing, because such a break changes no words and nothing else on the page would show it.

### Props

```ts
export interface DiffBlockRowProps {
  block: DiffBlock;
  pane: "A" | "B" | "UNIFIED";
  isActive?: boolean;
  isCollapsed?: boolean;
  showMoves?: boolean;
  onActivate?: (blockIndex: number) => void;
  onMeasured?: (blockId: string, pane: "A" | "B" | "UNIFIED", height: number) => void;
}
```

### Internal state

The row tracks measured height, focus-visible state, and collapsed-marker expansion. It does not own token data.

### Behaviour

For pane `A`, the row renders `a_tokens`; for pane `B`, it renders `b_tokens`; for pane `UNIFIED`, it renders `tokens`. A missing counterpart for `INSERTED` or `DELETED` renders a held-open gap or collapsed marker according to the row height policy in `DiffViewer`.

### Accessibility

The row is focusable when it is a navigation target. Its accessible label includes `BlockStatus`, `BlockKind`, and the available block ordinal.

### Edge, empty, and error states

Rows with no visible tokens render a marker rather than disappearing, because disappearance breaks block anchors and synchronized scrolling.

### Design tokens consumed

`DiffBlockRow` consumes `--color-ink`, `--color-paper`, `--color-vellum`, `--color-rule`, `--font-manuscript`, `--measure-prose`, and `--leading-manuscript`.

## TokenSpan

`TokenSpan` renders a `Token` with status-aware semantics.

### Props

```ts
export interface TokenSpanProps {
  token: Token;
  announceChanges?: boolean;
  compactUnchangedRun?: boolean;
}
```

### Internal state

`TokenSpan` has no mutable state. It is pure and memoized.

### Behaviour

| `TokenStatus` | Visual role | Text role |
|---|---|---|
| `UNCHANGED` | Plain manuscript text | Read normally. |
| `INSERTION` | Addition treatment from the design system | Included in reading order. |
| `DELETION` | Deletion treatment from the design system, shown through rather than removed | Included in reading order only when the user requests change announcements. |

When `announceChanges` is `false`, the prose should remain readable aloud. Insertions and deletions use visual treatment without prefixing every token. When `announceChanges` is `true`, contiguous changed runs receive a concise off-screen prefix such as "insertion:" or "deletion:" once per run, not once per token.

### Accessibility

The component avoids making screen readers announce punctuation-heavy diff syntax. By default, `TokenSpan` renders its `token.text` as ordinary text and adds no per-token ARIA prefix. When change announcements are enabled, `DiffBlockRow` groups adjacent `Token` payload objects with the same changed status into one announced run and wraps the group with a single off-screen prefix and suffix, for example "Insertion: ... end insertion" or "Deletion: ... end deletion". The grouping is by adjacent payload runs, not by words, and it is independent of `BlockMetrics` or `DiffMetrics` counts.

### Edge, empty, and error states

An empty `token.text` renders nothing but remains valid. Unknown statuses are impossible under the contract and should fail tests.

### Design tokens consumed

`TokenSpan` consumes `--color-addition`, `--color-addition-underlay`, `--color-deletion`, `--color-deletion-underlay`, `--color-ink`, and `--font-manuscript`.

## ChangeGutter

`ChangeGutter` renders block ordinals and compact status affordances.

### Props

```ts
export interface ChangeGutterProps {
  block: DiffBlock;
  pane: "A" | "B" | "UNIFIED";
  isActive?: boolean;
  onNavigate?: (blockIndex: number) => void;
}
```

### Internal state

The gutter tracks hover and focus-visible state only.

### Behaviour

For Manuscript A, the primary ordinal is `a_index`; for Manuscript B, it is `b_index`; for unified view, it shows both when both exist. The label is "block", not "line". Status badges use `BlockStatus` exactly.

### Accessibility

The gutter is not the only way to navigate. When interactive, it is a button labelled with the block ordinal and status.

### Edge, empty, and error states

When the relevant index is `null`, the gutter shows an insertion or deletion marker while preserving row height.

### Design tokens consumed

`ChangeGutter` consumes `--color-ink-muted`, `--color-rule`, `--color-rubric`, `--color-addition`, `--color-deletion`, `--color-moved`, and `--font-mono`.

## ViewModeToggle

`ViewModeToggle` switches between `ViewMode.SYNOPTIC` and `ViewMode.UNIFIED`.

### Props

```ts
export interface ViewModeToggleProps {
  value: ViewMode;
  onChange: (value: ViewMode) => void;
}
```

### Internal state

The toggle has focus-visible state only.

### Behaviour

The control writes `?view=synoptic` for `ViewMode.SYNOPTIC` and `?view=unified` for `ViewMode.UNIFIED`. It never changes `?block=` or `?moves=`.

### Accessibility

Use a two-option radiogroup or two pressed buttons with labels "Synoptic" and "Unified".

### Edge, empty, and error states

If there is not enough horizontal space for synoptic reading, the toggle remains available; responsive layout may recommend unified view but must not silently change `ViewMode`.

### Design tokens consumed

`ViewModeToggle` consumes `--color-ink`, `--color-ink-muted`, `--color-paper`, `--color-rule`, `--color-rubric`, and `--font-ui`.

## BlockConnector

`BlockConnector` draws correspondence between panes for changed or non-monotonic blocks.

### Props

```ts
export interface BlockConnectorProps {
  block: DiffBlock;
  aRect?: DOMRectReadOnly;
  bRect?: DOMRectReadOnly;
  showMoves?: boolean;
}
```

### Internal state

The connector tracks measured endpoints and animation frame id for repaint batching.

### Behaviour

The connector is decorative for `UNCHANGED` and usually omitted. It is meaningful for `MOVED`, `SPLIT`, and `MERGED`, and optional for `MODIFIED`. When `showMoves` is `false`, connectors for `MOVED` are hidden but the underlying `DiffBlock.status` is unchanged.

Connector reveal uses no drawing animation when `prefers-reduced-motion: reduce` is active; the connector appears or disappears immediately.

### Accessibility

The visual connector is `aria-hidden`. The corresponding `DiffBlockRow` exposes the relationship in text.

### Edge, empty, and error states

If either endpoint is unmounted by virtualization, the connector is not drawn. It returns when both endpoints are measured.

### Design tokens consumed

`BlockConnector` consumes `--color-moved`, `--color-moved-underlay`, `--color-rule`, and `--color-rubric`.

## EmptyState

`EmptyState` renders calm, actionable empty states for upload and comparison views.

### Props

```ts
export interface EmptyStateProps {
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}
```

### Internal state

`EmptyState` has no internal state.

### Behaviour

The component appears when no witness is selected, when both witnesses normalize to no comparable blocks, or when an expired comparison sends the researcher back to upload.

### Accessibility

The title is a heading at the appropriate page level. The optional action is a real button or link.

### Edge, empty, and error states

`EmptyState` must not be used for recoverable upload errors with a specific `code`; those belong next to the affected witness.

### Design tokens consumed

`EmptyState` consumes `--color-ink`, `--color-ink-muted`, `--color-vellum`, `--color-rule`, `--font-ui`, and `--font-manuscript`.
