This document defines the typography-first visual system for reading differences between Manuscript A and Manuscript B.

**Status:** Draft

**Related:** [Overview](./00-overview.md) · [Data schema](./05-data-schema.md) · [Frontend architecture](./08-frontend-architecture.md) · [Components](./10-components.md) · [Performance and scale](./11-performance-and-scale.md) · [ADR-0005](./adr/0005-tailwind-v4-css-first-tokens.md)

## The governing metaphor

A palimpsest is a manuscript scraped clean and overwritten, where the earlier text still shows faintly through. The interface follows that metaphor: deleted text shows through, it is not struck out in angry red. Insertions surface; deletions recede.

The design target is a book page, not a code review. A researcher may read this interface for an hour at a time, so sustained reading rhythm matters more than maximum density. Every choice below follows from that: warm paper, quiet ink, generous leading, restrained underlays, and marginal signals that help without taking over the page.

## Why code-diff conventions fail for prose

| Code-diff convention | Why it fails for prose | Palimpsest alternative |
|---|---|---|
| Full-bleed green and red row backgrounds | At prose density, repeated row fills create a strobing page and pull attention away from the sentence. | Use soft token underlays and marginal block markers, leaving the page field calm. |
| Monospace text | Monospace destroys reading rhythm, makes paragraphs wider than necessary, and often doubles the number of visual lines. | Use `--font-manuscript`, a serif text face with true italics and old-style figures. |
| Line-oriented gutters | Prose reflows with viewport width, zoom, font loading, and writing system. Visual lines are not stable anchors. | The change gutter shows block ordinals. These are block indices, not visual line numbers. |
| Character-level highlights inside justified prose | Dense inline highlights create visual noise and make the prose harder to read than the change itself. | Diff at token level by default, with understated underlays and non-colour redundant signals. |
| Pixel-linked split panes | Manuscript A and Manuscript B have different amounts of text, so pixel or percentage locks drift immediately. | Synchronize by aligned block anchors and display connectors for `MOVED`, `SPLIT`, and `MERGED` blocks. |
| Alignment hides original order | Putting corresponding passages on one row necessarily rearranges at least one witness, so a move can look stationary and a split can look pre-split. | Show each witness's original passage sequence before the aligned reading, with source and destination labels on structural items. |

## Typography

`--font-manuscript` is the text face for manuscript prose. `--font-ui` is the sans face for chrome, controls, summaries, and navigation. `--font-mono` is reserved for ids, metrics, and debugging values only.

The manuscript text must never be set in the UI font. UI chrome must never be set in the manuscript serif. Mixing the two erodes the distinction between reading surface and application controls.

Recommended open-licensed typefaces:

| Role | Recommendation | Fallback stack |
|---|---|---|
| `--font-manuscript` | Source Serif 4, Literata, or EB Garamond; choose a family with true italics, broad language support, and old-style figures. | `"Source Serif 4", "Literata", "EB Garamond", Georgia, "Times New Roman", serif` |
| `--font-ui` | Source Sans 3, Inter, or system UI. | `"Source Sans 3", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` |
| `--font-mono` | IBM Plex Mono or a platform monospace. | `"IBM Plex Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace` |

| Token | Value | Reason |
|---|---:|---|
| `--measure-prose` | `66ch` | A measure near 60-70 characters keeps sustained prose readable without forcing excessive eye travel. |
| `--leading-manuscript` | `1.7` | Generous leading preserves line discrimination when underlays, descenders, and old-style figures appear together. |

Use a modest modular type scale so manuscript text feels literary rather than dashboard-like:

| Role | Size | Line height |
|---|---:|---:|
| Footnote chrome | `0.8125rem` | `1.4` |
| Body UI | `0.9375rem` | `1.5` |
| Manuscript body | `1.125rem` | `var(--leading-manuscript)` |
| Section heading | `1.5rem` | `1.3` |
| Page title | `2rem` | `1.2` |

## Colour

Paper is warm off-white, not `#fff`, because a pure white page blooms on modern displays during long reading sessions. Ink is near-black, not `#000`, because pure black produces harsh edge contrast against warm paper. `--color-rubric` takes its name from the red initials and headings in medieval manuscripts.

### Opacity modifiers on text are prohibited

Verifying the tokens is not sufficient on its own. A component that writes `text-ink-muted/50` or `text-deletion/80` dilutes a compliant token into a non-compliant rendering, and the token table below will still look correct.

This is not hypothetical. During implementation, five call sites diluted tokens this way and produced measured ratios between 2.05:1 and 3.99:1 against paper — all well under AA, and all caught by the automated axe checks in the end-to-end suite rather than by inspection. If a quieter tone is genuinely needed, add a token for it and measure it.

Deleted text is the specific temptation and the specific prohibition. It must recede *without* becoming hard to read: the sense of showing through comes from the underlay and the hairline strike, never from fading the ink. A scholar reading a deletion is reading it as closely as anything else on the page.

### Light mode

| Token | Value | Use | Measured contrast |
|---|---|---|---:|
| `--color-ink` | `#1F1A14` | Primary manuscript and UI text on `--color-paper`. | 16.16:1 |
| `--color-ink-muted` | `#5F5548` | Secondary text on `--color-paper`. | 6.82:1 |
| `--color-paper` | `#FBF7EF` | Page background. | — |
| `--color-vellum` | `#F3E8D2` | Pane and card surface. `--color-ink` on it is 14.21:1. | — |
| `--color-rule` | `#D7C8AF` | Rules, quiet borders, disabled separators. | 1.54:1 against paper |
| `--color-rubric` | `#8F2E1F` | Accent text and active controls on `--color-paper`. | 7.62:1 |
| `--color-addition` | `#24563A` | Text accent for `INSERTION`. | 7.97:1 |
| `--color-addition-underlay` | `#DCEBDC` | Underlay for inserted tokens. | 1.16:1 against paper; ink remains 13.95:1 |
| `--color-deletion` | `#74413B` | Receded ink for `DELETION`. | 7.67:1 |
| `--color-deletion-underlay` | `#F0DED8` | Underlay for deleted tokens. | 1.22:1 against paper; ink remains 13.28:1 |
| `--color-moved` | `#5A4B8E` | Gutter marker and connector for moved block relationships. | 6.94:1 |
| `--color-moved-underlay` | `#E6E1F3` | Underlay for moved-block connector endpoints. | 1.20:1 against paper; ink remains 13.51:1 |

### Dark mode: lamplight

Lamplight mode keeps the metaphor of a page under a desk lamp: dark warm paper, softened ink, and saturated accents that still pass WCAG 2.2 AA for text.

| Token | Value | Use | Measured contrast |
|---|---|---|---:|
| `--color-ink` | `#EFE6D6` | Primary manuscript and UI text on `--color-paper`. | 14.36:1 |
| `--color-ink-muted` | `#BFAF98` | Secondary text on `--color-paper`. | 8.30:1 |
| `--color-paper` | `#1C1712` | Page background. | — |
| `--color-vellum` | `#282018` | Pane and card surface. `--color-ink` on it is 12.95:1. | — |
| `--color-rule` | `#594A3A` | Rules and separators. | 2.09:1 against paper |
| `--color-rubric` | `#E89A72` | Accent text and active controls on `--color-paper`. | 7.87:1 |
| `--color-addition` | `#9ED0A6` | Text accent for `INSERTION`. | 10.19:1 |
| `--color-addition-underlay` | `#25402E` | Underlay for inserted tokens. | 1.57:1 against paper; ink remains 9.16:1 |
| `--color-deletion` | `#E5A091` | Receded ink for `DELETION`. | 8.27:1 |
| `--color-deletion-underlay` | `#492A26` | Underlay for deleted tokens. | 1.39:1 against paper; ink remains 10.33:1 |
| `--color-moved` | `#C8B8F4` | Gutter marker and connector for moved block relationships. | 9.84:1 |
| `--color-moved-underlay` | `#39314F` | Underlay for moved-block connector endpoints. | 1.46:1 against paper; ink remains 9.82:1 |

Every text-bearing pair above exceeds WCAG 2.2 AA for normal text. Underlays are deliberately below 3:1 because they are not the only non-text signal and must not dominate the prose. The mandatory non-text contrast floor is 3:1 for gutter marker outlines, connector strokes, focus rings, and control borders; underlays may sit between 1.15:1 and 1.60:1 only when paired with those redundant channels.

## The diff visual language

Token-level cues and block-level cues use different channels. `INSERTION` and `DELETION` are `TokenStatus` values and can affect inline text. `MOVED`, `SPLIT`, and `MERGED` are `BlockStatus` values and must not be represented by tinting every token in a block.

### TokenStatus rendering

| `TokenStatus` | Rendering |
|---|---|
| `UNCHANGED` | Normal manuscript ink, no underlay, no decoration. |
| `INSERTION` | A token-bounded tinted underlay using `--color-addition-underlay`, a visible `+` prefix, medium-weight text using `--color-addition`, and a two-pixel underline offset away from the glyphs. |
| `DELETION` | A token-bounded `--color-deletion-underlay`, visible `−` prefix, deletion ink, and a two-pixel strike through the x-height. In synoptic view, deletions appear in Manuscript A only; unified view carries both readings inline. |

### BlockStatus rendering

| `BlockStatus` | Rendering |
|---|---|
| `UNCHANGED` | Normal block rhythm and a quiet block ordinal in the change gutter. |
| `MODIFIED` | Gutter marker indicating changed tokens; inline tokens carry `INSERTION` and `DELETION` treatments. |
| `INSERTED` | Block exists only in Manuscript B. The Manuscript B pane shows inserted content; the Manuscript A side reserves an alignment gap only when needed for synoptic reading. |
| `DELETED` | Block exists only in Manuscript A. The Manuscript A pane shows deleted content using the through-text treatment; Manuscript B reserves an alignment gap only when needed. |
| `MOVED` | Visible `Moved` sentence naming the A and B passage positions, plus gutter marker and a `BlockConnector` labelled `Moved up/down · A n → B n`. Optional endpoint underlay uses `--color-moved-underlay`; text itself is not recoloured as moved. |
| `SPLIT` | Visible `Split` sentence naming the one A passage and its B passages, plus connectors labelled `Split · A n → B n` for each member. Members share `group_id`; token tint never communicates the relationship. |
| `MERGED` | Visible `Merged` sentence naming the A passages and their one B passage, plus connectors labelled `Merged · A n → B n`. Members share `group_id`; token tint never communicates the relationship. |

`ARTIFACT` is a `BlockKind`, not a `BlockStatus`. `BlockKind.ARTIFACT` blocks are de-emphasised and collapsible. They use muted ink, smaller UI labeling, and no default participation in the main change rhythm because running heads, folio numbers, and footers are extracted but excluded from diff by default.

## Non-colour encoding is mandatory

Colour must never be the only signal. Roughly 1 in 12 men has a colour vision deficiency, and this is a reading tool rather than a decorative visualization.

Required redundant channels:

| Change | Non-colour channel |
|---|---|
| `INSERTION` | Visible `+`, tinted token box, two-pixel underline, and screen-reader text. |
| `DELETION` | Visible `−`, tinted token box, two-pixel strike, and screen-reader text. |
| `MOVED` | Text label and position sentence, diamond gutter marker, and connector. |
| `SPLIT` | Text label and passage sentence, forked gutter marker, and branching connector. |
| `MERGED` | Text label and passage sentence, joined gutter marker, and converging connector. |
| `BlockKind.ARTIFACT` | Collapsed disclosure label and muted block chrome. |

Inline ARIA uses hidden labels around changed tokens:

```tsx
<span className="sr-only">Insertion: </span>
<span data-token-status="INSERTION">new text </span>

<span className="sr-only">Deletion: </span>
<span data-token-status="DELETION">old text </span>
```

The visible `TokenSpan` should not be individually focusable unless it is the target of a jump. For block navigation, the focused `DiffBlockRow` announces the block ordinal, `BlockStatus`, and whether the row belongs to Manuscript A, Manuscript B, or unified view.

## The change gutter

The change gutter is a narrow marginal column carrying block ordinals and change markers: the manuscript-margin analogue of a diff gutter. It is not a line-number gutter.

| Property | Value |
|---|---|
| Width | `3.5rem` on desktop, `2.5rem` on narrow screens. |
| Ordinal | `DiffBlock.a_index` or `DiffBlock.b_index` where present; otherwise the available block index. |
| Typography | `--font-mono`, `0.75rem`, muted ink. |
| Sticky behavior | Sticky within the block row only when it improves scanability; it must not cover manuscript text. |

The ordinals are block indices, not visual line numbers. Prose reflows with viewport width, font loading, zoom, and writing system, so rendered visual lines are meaningless as anchors.

| `BlockStatus` | Marker |
|---|---|
| `UNCHANGED` | Quiet dot or no marker. |
| `MODIFIED` | Small vertical lozenge. |
| `INSERTED` | Plus marker. |
| `DELETED` | Minus marker. |
| `MOVED` | Diamond marker connected by `BlockConnector`. |
| `SPLIT` | Fork marker connected to grouped targets. |
| `MERGED` | Join marker connected from grouped sources. |

## Spacing, rhythm, and density

The baseline grid is derived from `--leading-manuscript`. Manuscript paragraphs use `1lh` block spacing by default, with headings and verse lines adjusted by `BlockKind` rather than by arbitrary margins.

Verse departs from the paragraph rhythm in two specific ways, and both are legibility rather than decoration:

| Treatment | Reason |
|---|---|
| Tighter block spacing than a paragraph | Verse lines are lines of one poem, not consecutive paragraphs. Paragraph spacing sets a stanza double-spaced and destroys its shape on the page. |
| Hanging indent on wrap | A verse line too long for the measure must wrap so that the reader cannot mistake the wrap for a line break. In poetry the line break is the meaning, and a false one misreads the poem. |
| A line opening a stanza takes the space back | The blank line between stanzas is part of the poem's form, not slack in the layout. |
| A break one witness lacks is marked | A stanza break that changed between witnesses alters no words, so nothing else on the page would show it. It carries the moved treatment, because that is what it is: a structural change with no wording change. |

The system deliberately chooses generous whitespace over information density. Dense rows make prose behave like log output; `palimpsest` should behave like an annotated page. Alignment gaps in synoptic view are allowed when they preserve correspondence between Manuscript A and Manuscript B. They are preferable to compressing the text or faking pixel-linked scroll.

## Tailwind v4 implementation

Tailwind v4 is CSS-first. The global stylesheet imports Tailwind in one line, defines design tokens in `@theme`, uses `@source` only for content overrides that Tailwind cannot discover, and relies on `@tailwindcss/postcss` as the PostCSS plugin. There is no `tailwind.config.js`; it is deprecated in favour of this CSS-first setup for `palimpsest`.

Every `@theme` token is auto-emitted as a CSS custom property on `:root`, which makes lamplight mode a simple override. See [ADR-0005](./adr/0005-tailwind-v4-css-first-tokens.md).

```css
@import "tailwindcss";

@source "../app/**/*.{ts,tsx}";
@source "../components/**/*.{ts,tsx}";
@source "../lib/**/*.{ts,tsx}";

@theme {
  --color-ink: #1F1A14;
  --color-ink-muted: #5F5548;
  --color-paper: #FBF7EF;
  --color-vellum: #F3E8D2;
  --color-rule: #D7C8AF;
  --color-rubric: #8F2E1F;
  --color-addition: #24563A;
  --color-addition-underlay: #DCEBDC;
  --color-deletion: #74413B;
  --color-deletion-underlay: #F0DED8;
  --color-moved: #5A4B8E;
  --color-moved-underlay: #E6E1F3;
  --font-manuscript: "Source Serif 4", "Literata", "EB Garamond", Georgia, "Times New Roman", serif;
  --font-ui: "Source Sans 3", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: "IBM Plex Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  --measure-prose: 66ch;
  --leading-manuscript: 1.7;
}

:root[data-theme="lamplight"] {
  --color-ink: #EFE6D6;
  --color-ink-muted: #BFAF98;
  --color-paper: #1C1712;
  --color-vellum: #282018;
  --color-rule: #594A3A;
  --color-rubric: #E89A72;
  --color-addition: #9ED0A6;
  --color-addition-underlay: #25402E;
  --color-deletion: #E5A091;
  --color-deletion-underlay: #492A26;
  --color-moved: #C8B8F4;
  --color-moved-underlay: #39314F;
}
```

## Motion

Motion is minimal by principle. The allowed transitions are:

| Interaction | Motion |
|---|---|
| View mode change | Short opacity and layout transition that preserves reading position. |
| Scroll-to-block | Smooth scroll only when `prefers-reduced-motion` is not set. |
| Connector reveal | Subtle fade for `BlockConnector`, not a drawing animation. |

When `prefers-reduced-motion: reduce` is active, transitions are removed and scroll-to-block jumps immediately.

## Print

Researchers will print or PDF comparisons, so print output is part of the design system.

The print stylesheet forces unified view because side-by-side panes waste paper and often become unreadable. Underlays convert to patterns that survive greyscale: insertions use a light underline pattern, deletions retain the hairline strike, and moved-block relationships use labelled gutter markers rather than colour. The change gutter remains visible with block ordinals and `BlockStatus` markers, because those ordinals are the stable citation anchors on paper as well as on screen.

### Printing must not print a window

Both reading surfaces are virtualized, so only rows near the viewport exist in the DOM. Printing in that state puts a fraction of the collation on paper — measured at 42 of 300 blocks from synoptic view — with nothing on the page to indicate anything is missing. That is the same failure as rendering a truncated comparison as a whole one, except the artifact leaves the building and is the kind of thing that gets cited.

Virtualization is therefore suspended for the duration of a print: `usePrintAll` watches `beforeprint`, `afterprint`, and the `print` media query, and both views take a `renderAll` prop that renders every row.

The state update must be flushed synchronously. React batches updates, and the browser snapshots the document as soon as the `beforeprint` handler returns, so an ordinary update lands after the snapshot and prints exactly the fragment it was meant to prevent. The media query is watched as well as the event, which makes the behaviour testable under emulated print media and covers browsers that switch media without firing the event.
