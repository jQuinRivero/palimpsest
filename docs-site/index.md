# palimpsest guide

`palimpsest` is an open-source literary-criticism web app for comparing two witnesses of a text: Manuscript A and Manuscript B.

This site is the user-facing guide plus a short architecture tour. It is not the normative specification. The specification remains in [`docs/`](reference.md), and this site links to it when an implementation detail matters.

## Start here

- New readers: [What palimpsest is](guide/index.md)
- Running it locally: [Install and run](guide/install.md)
- First comparison: [Quickstart](guide/quickstart.md)
- Deciding whether to trust or extend it: [Architecture](architecture/index.md)

## The core idea

Code diff tools are line-oriented, monospace, and optimized for patch review. That is wrong for sustained prose: a reflowed paragraph looks like a rewrite, and a moved passage often disappears into noise. palimpsest aligns blocks first, compares word tokens second, and renders the result for reading.
