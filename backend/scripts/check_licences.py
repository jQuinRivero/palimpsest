"""Audit installed dependency licences.

The repo is Apache-2.0, so copyleft is disqualifying — see ADR-0002. This
checks every installed distribution, not just the direct dependencies, because
a copyleft transitive dependency is just as much of a problem.

    uv run python scripts/check_licences.py
"""

from importlib.metadata import distributions

COPYLEFT_TOKENS = ("GPL", "AGPL", "LGPL", "MPL", "EUPL", "CDDL", "SLEEPYCAT")
# Strong copyleft is a hard block. LGPL and MPL are weak copyleft and may be
# acceptable, but they warrant a conscious decision rather than a silent import.
HARD_BLOCK_TOKENS = ("AGPL", "GPLV2", "GPLV3", "GPL2", "GPL3")


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


def main() -> int:
    rows = []
    for dist in distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        rows.append((name.lower(), name, dist.version, licence_of(dist)))
    rows.sort()

    print(f"{'package':26} {'version':12} licence")
    print("-" * 78)

    flagged: list[tuple[str, str, bool]] = []
    for _, name, version, licence in rows:
        print(f"{name:26} {version:12} {licence}")
        normalised = licence.upper().replace(" ", "").replace("-", "").replace(".", "")
        if any(token in normalised for token in COPYLEFT_TOKENS):
            hard = any(token in normalised for token in HARD_BLOCK_TOKENS)
            flagged.append((name, licence, hard))

    print()
    if not flagged:
        print("No copyleft dependencies. Compatible with Apache-2.0.")
        return 0

    print("COPYLEFT FOUND:")
    for name, licence, hard in flagged:
        print(f"  {'BLOCK ' if hard else 'REVIEW'}  {name}: {licence}")
    return 1 if any(hard for _, _, hard in flagged) else 0


if __name__ == "__main__":
    raise SystemExit(main())
