"""Fail if a lockfile names a package index other than canonical PyPI.

Lockfiles record whichever index resolved them. Regenerating one on a machine
behind a private package proxy silently bakes that proxy's host, and often an
organization or feed identifier, into a file every contributor and every CI run
installs from. The result is a repository that publishes internal
infrastructure detail and that only installs while the private feed happens to
allow anonymous reads.

`uv sync --frozen` fetches the URLs a lock names verbatim and ignores index
configuration, so this cannot be corrected at install time. It has to be
correct in the committed file, which is what this script enforces.

Run `Relock` (.github/workflows/relock.yml) to regenerate the locks on a runner
with direct PyPI access rather than editing them by hand.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LOCKFILES = ("backend/uv.lock", "docs-site/uv.lock")

ALLOWED_REGISTRIES = frozenset({"https://pypi.org/simple"})
ALLOWED_ARTIFACT_HOSTS = ("https://files.pythonhosted.org/",)

# Reported by name so a failure says what leaked, not merely that something did.
PRIVATE_MARKERS = (
    (
        "Azure DevOps feed (visualstudio.com)",
        re.compile(r"[\w-]+\.pkgs\.visualstudio\.com"),
    ),
    ("Azure DevOps feed (dev.azure.com)", re.compile(r"pkgs\.dev\.azure\.com")),
    ("internal package proxy", re.compile(r"packagefeedproxy\.[\w.-]+")),
)


def check(relative: str) -> list[str]:
    path = ROOT / relative
    if not path.is_file():
        return [f"{relative}: missing"]

    raw = path.read_text(encoding="utf-8")
    problems: list[str] = []

    for label, pattern in PRIVATE_MARKERS:
        hits = pattern.findall(raw)
        if hits:
            problems.append(f"{relative}: {len(hits)} reference(s) to a {label}")

    document = tomllib.loads(raw)
    for package in document.get("package", []):
        name = package.get("name", "<unnamed>")

        registry = package.get("source", {}).get("registry")
        if registry is not None and registry not in ALLOWED_REGISTRIES:
            problems.append(f"{relative}: {name} resolves from {registry}")

        artifacts = [package.get("sdist"), *package.get("wheels", [])]
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            url = artifact.get("url")
            if url and not url.startswith(ALLOWED_ARTIFACT_HOSTS):
                host = url.split("/")[2] if "//" in url else url
                problems.append(f"{relative}: {name} downloads from {host}")

    return problems


def main() -> int:
    problems: list[str] = []
    for relative in LOCKFILES:
        found = check(relative)
        problems.extend(found)
        if not found:
            print(f"[PASS] {relative}: canonical PyPI only")

    # One line per distinct problem, capped: a mis-resolved lock produces
    # thousands of identical findings, and the first few already say it.
    for problem in sorted(set(problems))[:20]:
        print(f"[FAIL] {problem}")

    if problems:
        distinct = len(set(problems))
        print(f"\nLockfile index check: {distinct} distinct problem(s).")
        print("Run the Relock workflow to regenerate the locks against PyPI.")
        return 1

    print("\nLockfile index check: 0 problems.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
