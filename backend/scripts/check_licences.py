"""Audit installed dependency licences.

The repo is Apache-2.0, so copyleft is disqualifying — see ADR-0002. This
checks every installed Python distribution and, when requested, the installed
npm tree. Transitive dependencies matter as much as direct dependencies.

    uv run python scripts/check_licences.py
    python scripts/check_licences.py --npm-only
"""

from __future__ import annotations

import argparse
import re
from importlib.metadata import distributions

from third_party_notices import PackageNotice, installed_npm_packages

REVIEW_PATTERNS = (
    re.compile(r"(^|[^A-Z])MPL([^A-Z]|$)"),
    re.compile(r"(^|[^A-Z])LGPL([^A-Z]|$)"),
    re.compile(r"(^|[^A-Z])EUPL([^A-Z]|$)"),
    re.compile(r"(^|[^A-Z])CDDL([^A-Z]|$)"),
    re.compile(r"SLEEPYCAT"),
)
HARD_BLOCK_PATTERNS = (
    re.compile(r"(^|[^A-Z])AGPL([^A-Z]|$)"),
    re.compile(r"(^|[^A-Z])GPL([^A-Z]|$)"),
    re.compile(r"(^|[^A-Z])SSPL([^A-Z]|$)"),
)


def licence_of(dist: object) -> str:
    meta = dist.metadata  # type: ignore[attr-defined]
    value = meta.get("License-Expression") or ""
    if not value or len(value) > 60:
        classifiers = [c for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")]
        if classifiers:
            value = "; ".join(c.split("::")[-1].strip() for c in classifiers)
    if not value:
        value = (meta.get("License") or "?")[:60].replace("\n", " ")
    return value


def normalise_licence(licence: str) -> str:
    return licence.upper().replace(" ", "").replace("-", "").replace(".", "")


def needs_review(licence: str) -> bool:
    normalised = normalise_licence(licence)
    return any(pattern.search(normalised) for pattern in REVIEW_PATTERNS)


def is_hard_block(licence: str) -> bool:
    normalised = normalise_licence(licence)
    without_weak_prefixes = normalised.replace("LGPL", "").replace("MPL", "")
    return any(pattern.search(without_weak_prefixes) for pattern in HARD_BLOCK_PATTERNS)


def print_rows(title: str, rows: list[PackageNotice]) -> list[tuple[str, str, bool]]:
    print(title)
    print(f"{'package':26} {'version':12} licence")
    print("-" * 78)

    flagged: list[tuple[str, str, bool]] = []
    for row in rows:
        print(f"{row.name:26} {row.version:12} {row.licence}")
        hard = is_hard_block(row.licence)
        if hard or needs_review(row.licence):
            flagged.append((row.name, row.licence, hard))
    print()
    return flagged


def python_rows() -> list[PackageNotice]:
    rows = []
    for dist in distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        rows.append(
            PackageNotice(
                ecosystem="Python",
                name=name,
                version=dist.version,
                licence=licence_of(dist),
                attribution="",
                group="",
            )
        )
    return sorted(rows, key=lambda row: row.sort_key)


def report(flagged: list[tuple[str, str, bool]]) -> int:
    print()
    if not flagged:
        print("No copyleft dependencies. Compatible with Apache-2.0.")
        return 0

    print("COPYLEFT FOUND:")
    for name, licence, hard in flagged:
        print(f"  {'BLOCK ' if hard else 'REVIEW'}  {name}: {licence}")
    return 1 if any(hard for _, _, hard in flagged) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--npm-only", action="store_true", help="audit only frontend/node_modules")
    parser.add_argument(
        "--python-only", action="store_true", help="audit only the current Python env"
    )
    args = parser.parse_args()

    flagged: list[tuple[str, str, bool]] = []
    if not args.npm_only:
        flagged.extend(print_rows("Python dependencies", python_rows()))
    if not args.python_only:
        flagged.extend(print_rows("npm dependencies", installed_npm_packages()))
    return report(flagged)


if __name__ == "__main__":
    raise SystemExit(main())
