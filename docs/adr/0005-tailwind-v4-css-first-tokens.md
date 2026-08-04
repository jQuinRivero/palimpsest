# ADR-0005 — Adopt Tailwind v4 CSS-first tokens

**Status:** Accepted
**Related:** [Frontend architecture](../08-frontend-architecture.md) · [Design system](../09-design-system.md) · [Components](../10-components.md)

## Context

Tailwind CSS 4.3.3 moved the default configuration model out of JavaScript and into CSS. `@import "tailwindcss"` replaces the three `@tailwind` directives, design tokens live in an `@theme` block, content paths are auto-detected with `@source` for overrides, and the PostCSS plugin is now `@tailwindcss/postcss`. A legacy `tailwind.config.js` still works through `@config`, but it is no longer the default pattern.

`palimpsest` is a typography- and colour-critical reading application. Its visual language is a small manuscript-inspired token set: `--color-ink`, `--color-paper`, `--color-vellum`, `--color-rubric`, addition, deletion, and moved underlays, `--font-manuscript`, and `--measure-prose`.

## Options considered

- Tailwind v4 CSS-first configuration. It matches the current Tailwind default, improves build performance, and emits `@theme` tokens as CSS custom properties on `:root`.
- Tailwind v4 with a legacy `@config` JavaScript file. It preserves the older mental model, helps contributors familiar with v3, and may ease compatibility with plugins that still expect JavaScript configuration.
- Pinning to Tailwind v3. It has a larger body of examples and plugin compatibility. It also starts a greenfield project on the older configuration model and gives up v4's build improvements.
- Plain CSS modules or vanilla-extract. Either could express a small design system clearly and avoid Tailwind-specific conventions. They would also forfeit Tailwind's utility workflow and the shared vocabulary many frontend contributors already know.

## Decision

Adopt Tailwind v4 CSS-first `@theme` tokens and do not create a `tailwind.config.js` by default.

The specific reason this suits `palimpsest` is that every `@theme` token is automatically emitted as a CSS custom property on `:root`. Because the reader depends on manuscript tokens such as `--color-ink`, `--color-paper`, `--color-vellum`, `--color-rubric`, `--color-addition-underlay`, `--color-deletion-underlay`, `--color-moved-underlay`, `--font-manuscript`, and `--measure-prose`, real CSS variables make the dark-mode lamplight variant a plain override and make the print stylesheet straightforward. Neither requires a JavaScript build step to reason about design tokens.

## Consequences

A greenfield project pays no migration cost and gets the v4 build-performance improvement immediately. The design system can document real CSS variables rather than translating JavaScript configuration into runtime styles.

The cost is contributor familiarity and ecosystem lag. Contributors who know Tailwind v3 need to learn that the actual token source is the CSS `@theme` block in [Design system](../09-design-system.md). Some older plugins and community examples assume `tailwind.config.js`, so adopting them may require adaptation or rejection. Revisit this decision only if a required plugin proves incompatible with CSS-first configuration.
