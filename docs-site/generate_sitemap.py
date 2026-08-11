#!/usr/bin/env python
"""Write sitemap.xml by walking the built HTML.

`sphinx-sitemap` collects pages through Sphinx's per-page events, and that
collection did not survive the build as it runs in CI: an identical revision
produced sixteen URLs locally and one on the runner. A sitemap that is silently
almost empty is worse than none, because nothing downstream complains -- it
simply stops being an index of the site.

Reading the output directory instead removes the discrepancy by construction.
Whatever HTML was published is exactly what gets listed, on any machine, with
no dependency on build ordering, parallelism, or Sphinx internals. It also
drops two dependencies from the documentation toolchain.

Usage: generate_sitemap.py <html-dir> <base-url>
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Search and index pages are navigation, not content. Listing them invites a
# search engine to rank them for queries the real pages should answer.
EXCLUDED = {"search.html", "genindex.html", "py-modindex.html", "404.html"}


def page_urls(root: Path, base_url: str) -> list[str]:
    urls: list[str] = []
    for path in sorted(root.rglob("*.html")):
        if path.name in EXCLUDED:
            continue
        # _static, _sources, and _images hold assets and copies of the source,
        # not pages a reader should land on from a search result.
        relative = path.relative_to(root)
        if any(part.startswith("_") for part in relative.parts):
            continue
        urls.append(base_url + relative.as_posix())
    return urls


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    base_url = sys.argv[2]
    if not base_url.endswith("/"):
        base_url += "/"

    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1

    urls = page_urls(root, base_url)
    if not urls:
        print(f"error: no pages found under {root}", file=sys.stderr)
        return 1

    urlset = ElementTree.Element("urlset", xmlns=SITEMAP_NS)
    for url in urls:
        ElementTree.SubElement(ElementTree.SubElement(urlset, "url"), "loc").text = url

    tree = ElementTree.ElementTree(urlset)
    ElementTree.indent(tree, space="  ")
    output = root / "sitemap.xml"
    tree.write(output, encoding="utf-8", xml_declaration=True)

    print(f"wrote {output} with {len(urls)} URLs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
