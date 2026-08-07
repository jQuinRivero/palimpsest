"""Validate documentation links that point back into this repository.

The Jupyter Book site links to the normative specification through GitHub
``blob/main`` URLs. Those URLs return 404 while the repository is private, so
Sphinx cannot check them honestly before release. Ignoring every external URL
made the link-check job green, but also made it meaningless.

This checker maps each repository URL back to the working tree and verifies the
target directly. Sphinx then checks every other external URL normally.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "docs-site"
REPOSITORY_PREFIX = "https://github.com/jQuinRivero/palimpsest/blob/main/"
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")


def repository_target(url: str) -> Path | None:
    """Return the local target for one GitHub blob URL, if it is ours."""
    if not url.startswith(REPOSITORY_PREFIX):
        return None
    relative = unquote(urlparse(url).path.split("/blob/main/", maxsplit=1)[1])
    return ROOT / relative


def main() -> int:
    checked = 0
    failures: list[str] = []

    for source in sorted(SITE.rglob("*.md")):
        if any(part in {"_build", ".venv"} for part in source.relative_to(SITE).parts):
            continue
        for line_number, line in enumerate(
            source.read_text(encoding="utf-8").splitlines(), 1
        ):
            for url in MARKDOWN_LINK.findall(line):
                target = repository_target(url)
                if target is None:
                    continue
                checked += 1
                if not target.is_file():
                    failures.append(
                        f"{source.relative_to(ROOT)}:{line_number}: "
                        f"{url} points at missing {target.relative_to(ROOT)}"
                    )

    if failures:
        print("\n".join(failures))
        return 1

    print(f"Checked {checked} links from the guide into the normative specification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
