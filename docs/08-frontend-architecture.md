This document defines the frontend architecture for uploading witnesses, fetching `ComparisonResult` payloads, and rendering them without client-side collation.

**Status:** Draft

**Related:** [Overview](./00-overview.md) · [Data schema](./05-data-schema.md) · [API reference](./06-api-reference.md) · [Design system](./09-design-system.md) · [Components](./10-components.md) · [Performance and scale](./11-performance-and-scale.md) · [ADR-0004](./adr/0004-server-side-diff-computation.md)

## Stack and rationale

| Choice | Version floor | Rationale |
|---|---:|---|
| Next.js App Router | 16.3.0 | The App Router is the default and recommended Next.js architecture; it gives `palimpsest` server components, nested route boundaries, and streaming where they help first paint. |
| React | 19 | React 19 is the rendering model assumed by Next.js 16 and lets the app keep interaction local without adding an application state framework. |
| Tailwind CSS | 4.3.3 | Tailwind v4 is CSS-first, which matches the design-system requirement that tokens live in CSS custom properties rather than a JavaScript configuration file. |
| `react-virtuoso` | 4.18.11 | The viewer renders variable-height prose blocks; fixed-row virtualization is wrong because manuscript blocks reflow with viewport width and content density. |

No client-side diffing library is needed at all. The backend computes the collation and returns a finished `ComparisonResult`; the browser only renders typed blocks and tokens. The npm `diff-match-patch` package is frozen at 2018 and irrelevant here, both because it is stale and because client-side diffing would violate [ADR-0004](./adr/0004-server-side-diff-computation.md).

## Directory structure

```text
frontend/
  app/
    layout.tsx                 # Root shell, metadata, global styles, font variables.
    page.tsx                   # Upload route for Manuscript A and Manuscript B.
    c/
      [comparisonId]/
        page.tsx               # Viewer route; server component fetches the comparison.
    error.tsx                  # Route-level error boundary for recoverable rendering failures.
    not-found.tsx              # Expired or unknown comparison/document states.
  components/
    ManuscriptUploader.tsx     # Upload form and witness metadata display.
    DiffViewer.tsx             # Top-level interactive viewer composition; contains ViewModeToggle.
    VirtualizedSynopticView.tsx # Virtualized synoptic grid; supersedes SyncScrollContainer.
    DiffSummaryBar.tsx         # Metrics and navigation summary.
    DiffBlockRow.tsx           # One rendered `DiffBlock`.
    TokenSpan.tsx              # One rendered `Token`.
    ChangeGutter.tsx           # Block ordinals and block-level change markers.
    ChangeNavigator.tsx        # Next/previous change controls and their announcements.
    BlockConnector.tsx         # Visual connector for aligned block pairs and moves.
    EmptyState.tsx             # Helpful state for no upload, no changes, or expired links.
  lib/
    api.ts                     # Typed API wrapper and `problem+json` handling.
    types.ts                   # TypeScript mirror of the Pydantic models; see doc 05.
    hooks/
      useBlockNavigation.ts    # Active block and next/previous change navigation.
  styles/
    globals.css                # Tailwind v4 import, `@theme` tokens, base document styles.
```

There is no `loading.tsx`; see [Route-level `loading.tsx` is deliberately absent](#route-level-loadingtsx-is-deliberately-absent).

There is also no `useComparison` hook. The viewer route is a **server** component that awaits `getComparison` directly, so the payload arrives with the first byte of HTML and there is no client-side loading state to orchestrate. This is what makes an unknown comparison return a real `404`, and it means a shared `?block=` link is correct on first paint rather than after a hydration correction. Client-side fetching returns only if the accepted-and-poll path needs to surface progress in the viewer, which today it does not — polling happens in the uploader before redirect.

Document [10](./10-components.md) owns component props and internal component state. This document only fixes the architectural responsibilities and the seams between routing, fetching, rendering, and interaction.

## Routes

| Route | Purpose | Data boundary |
|---|---|---|
| `/` | Uploader for Manuscript A and Manuscript B. | Creates or selects two `DocumentSummary` records and requests a comparison. |
| `/c/[comparisonId]` | Shareable viewer for one persisted comparison. | Fetches `GET /api/v1/comparisons/{comparison_id}` or, for large comparisons, a windowed block page. |

The primary flow is:

1. The researcher uploads both witnesses on `/`.
2. The client posts each witness to `POST /api/v1/documents` if the backend stores documents independently.
3. The client creates the collation with `POST /api/v1/comparisons`.
4. A `201` response redirects to the App Router route `/c/[comparisonId]`, concretely `/c/<comparison_id>`.
5. A `202` response enters the accepted-polling path until the comparison is available, then redirects to `/c/[comparisonId]`, concretely `/c/<comparison_id>`.

The comparison URL is the shareable artifact. Persistent storage exists so a researcher can send `/c/<comparison_id>` to a colleague and both people can read the same `ComparisonResult` until `expires_at`.

## Server and client components

The `/c/[comparisonId]` route fetches the `ComparisonResult` in a server component. That is the default for the viewer route because it gives a fast first paint, avoids a client waterfall, and keeps backend credentials or deployment-only API configuration out of browser code.

```tsx
// app/c/[comparisonId]/page.tsx
export default async function ComparisonPage({
  params,
  searchParams,
}: {
  params: Promise<{ comparisonId: string }>;
  searchParams: Promise<{ view?: string; block?: string; moves?: string }>;
}) {
  // Fetch `ComparisonResult` on the server and pass it to `DiffViewer`.
}
```

The server component validates route and query state, resolves `comparisonId`, fetches the comparison, and renders error or not-found states through App Router boundaries. It then hands immutable data to `DiffViewer`.

These components must be `"use client"`:

| Component or hook | Why it is client-side |
|---|---|
| `DiffViewer` | Owns interactive view state, keyboard navigation, active block, and composition of the virtualized view. |
| `VirtualizedSynopticView` | Runs `react-virtuoso`, which measures rendered rows in the browser. |
| `ViewModeToggle` | Mutates URL state in response to user interaction. |
| `DiffBlockRow`, when virtualized | Runs inside `react-virtuoso` and participates in measured, variable-height rendering. |
| `TokenSpan`, when announcing inline changes | May carry interactive focus and screen-reader-only labels. |
| `ChangeNavigator` and `useBlockNavigation` | Handle keyboard events, focus management, live announcements, and URL replacement for the active block. |

Very large payloads use the windowed path defined in [Performance and scale](./11-performance-and-scale.md): `GET /api/v1/comparisons/{comparison_id}/blocks?offset=&limit=`. The server route should request `GET /api/v1/comparisons/{comparison_id}?include_blocks=false` when the full `blocks` array would exceed the rendering budget. In that mode, the server sends metadata and initial URL state, and the client fetches `BlockPage` windows as the virtualizer approaches unloaded ranges. The switch is driven by `truncated: true`, `total_blocks`, and response-size limits from doc 11, not by ad hoc browser heuristics.

### Route-level `loading.tsx` is deliberately absent

A `loading.tsx` file creates a Suspense boundary around the whole route. Next.js then flushes the HTTP response — status line included — before the page component has finished awaiting its data, so a later `notFound()` renders the correct not-found *body* under a `200 OK` *status*.

That is unacceptable here. A comparison URL is meant to be shared and cited, so an expired or unknown one must be knowably gone: `404` for unknown, mapped from the API's `COMPARISON_NOT_FOUND`, and likewise for the `410` of `COMPARISON_EXPIRED`. Returning `200` would tell a crawler, a link checker, or a reference manager that a dead comparison is alive.

The viewer route therefore has no `loading.tsx`. This was verified against a production build: with the file present `/c/{unknown}` returned `200`; with it removed, `404`. The page issues a single fast request, so there is little to gain from streaming a skeleton. If a loading state is wanted later it must sit in a Suspense boundary *inside* the page, below the point where the not-found decision has already been made.

## URL as state

The URL state is part of the scholarly contract:

| Parameter | Values | Meaning |
|---|---|---|
| `view` | `synoptic` or `unified` | Rendering mode. |
| `block` | `<index>` | Active block index, not a rendered visual line. |
| `moves` | `on` or `off` | Whether move connectors are shown. |

A researcher must be able to send a colleague a link to a specific passage in a specific view. This is a scholarly-citation requirement, not a convenience.

State synchronizes to the URL with shallow routing. View changes and explicit navigation may use `push` so the browser back button returns to a meaningful prior view. Scroll-driven `block` updates must use `replace`, not `push`, so reading through a comparison does not pollute browser history with every block anchor.

`block` is always a block index. It is never a rendered visual line number. Prose reflows with viewport width, font loading, zoom, and writing system; visual lines are therefore meaningless as anchors. The gutter shows block ordinals.

## Data fetching and the API client

`lib/api.ts` is the only place that knows the REST surface:

```ts
export async function getComparison(
  comparisonId: string,
  options?: { includeBlocks?: boolean },
): Promise<ComparisonResult> {
  // Calls `GET /api/v1/comparisons/{comparison_id}`.
}

export async function getComparisonBlocks(
  comparisonId: string,
  params: { offset: number; limit: number },
): Promise<BlockPage> {
  // Calls `GET /api/v1/comparisons/{comparison_id}/blocks`.
}
```

TypeScript types mirror the Pydantic models in [Data schema](./05-data-schema.md). The frontend does not invent alternate names for `ComparisonResult`, `DiffBlock`, `Token`, `BlockStatus`, `TokenStatus`, or `ViewMode`; JSON remains `snake_case` on the wire.

Errors use the RFC 9457 `application/problem+json` shape from [API reference](./06-api-reference.md): `type`, `title`, `status`, `detail`, and `code`. `lib/api.ts` should parse that shape into a typed application error and preserve the backend `code`, including `COMPARISON_NOT_FOUND`, `COMPARISON_EXPIRED`, `DIFF_BUDGET_EXCEEDED`, and `RATE_LIMITED`.

`POST /api/v1/comparisons` may return `202` with an accepted comparison. The uploader enters a polling path with bounded exponential backoff and jitter, displays progress copy that does not promise completion timing, and stops cleanly on terminal `problem+json` errors. Because polling completes before the redirect, the viewer route always loads a finished comparison. `error.tsx` handles rendering and data exceptions; `not-found.tsx` handles unknown or expired artifacts; server fetch latency is absorbed by the server render itself rather than by a route-level loading state.

## State management

Use React state plus URL parameters. Do not introduce Redux, Zustand, or another global store for v1.

The reason is structural: the `ComparisonResult` payload is immutable once fetched, and the interactive state is tiny. The viewer needs only:

| State | Owner |
|---|---|
| View mode | The viewer route, backed by `?view=synoptic\|unified`, resolved server-side so the first paint is already the requested mode. |
| Active block | `useBlockNavigation`, backed by `?block=<index>`, seeded from the server for the same reason. |
| Move connector visibility | `DiffViewer`, backed by `?moves=on\|off`. |
| Scroll position | `react-virtuoso` inside `VirtualizedSynopticView`; no application-level scroll state exists. |

`useBlockNavigation` owns next/previous change traversal, focus, live announcements, and active block updates, and is the only custom hook in the application. Anything beyond it should be justified by doc 10 rather than added as a hidden architecture choice.

## Scroll alignment

The two panes are not synchronized, because they are not two scrollers. Synoptic view is a **single** virtualized list whose every row is a three-cell grid — Manuscript A, connector, Manuscript B — so corresponding blocks share a row and are aligned by layout. There is one scroll position and drift is not merely corrected but structurally impossible.

The original design solved this the other way, with an anchor-linked algorithm reconciling two independent scrollers after every layout pass. That design was sound and is preserved in [Components](./10-components.md), because it is still what an independently scrolling view would need — a [roadmap](./14-roadmap.md) item. It was not needed here: the problem could be removed instead of solved.

The cost is real and stated plainly: the panes cannot be scrolled independently, so a researcher cannot hold one witness still while ranging over the other, and a single very tall block makes both cells tall.

`MOVED`, `SPLIT`, and `MERGED` blocks may have connectors, but a connector is a visual aid. The grid row, not the connector, is what puts counterparts side by side.

## Accessibility and progressive enhancement

The viewer must support keyboard navigation between changed blocks. The required shortcuts are next change and previous change; doc 10 owns the exact control labels and props. When jumping to a block, focus moves to the changed block container or the first changed `TokenSpan` inside it, and the URL `block` parameter updates with `replace`.

Motion is minimal and must honor `prefers-reduced-motion`. Smooth scroll-to-block is allowed only when the user has not requested reduced motion; otherwise jumps are immediate.

Inline insertions and deletions need non-colour cues and screen-reader text, as specified in [Design system](./09-design-system.md). The application must not rely on green/red colour alone to convey textual change.

Without JavaScript, `/c/[comparisonId]` still returns server-rendered comparison metadata and a readable initial view, because the payload is fetched on the server. Interaction degrades: view toggling, virtualized row loading, keyboard jump navigation, and accepted polling require JavaScript. The no-JavaScript fallback should therefore prefer a unified, fully rendered excerpt or an honest message linking to reload when the comparison is ready.

## Build and development

Development runs the Next.js app and FastAPI app on separate ports. `next dev` serves the frontend; `uvicorn` serves the backend API. CORS is allowed only for the development frontend origin and is not a production integration mechanism.

Production builds the frontend with the normal Next.js build path and serves it as the web application entry point. The backend remains the authority for parsing, collation, storage, and API responses. Whether the two processes share a host or are deployed behind one reverse proxy, browser code calls only the documented `/api/v1` paths.

Tailwind v4 uses `@tailwindcss/postcss`. There is no `tailwind.config.js`; tokens live in CSS through `@theme`, as detailed in [Design system](./09-design-system.md) and [ADR-0005](./adr/0005-tailwind-v4-css-first-tokens.md).
