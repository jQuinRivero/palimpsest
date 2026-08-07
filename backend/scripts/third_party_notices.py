"""Generate third-party dependency notices for the installed trees.

Run from ``backend/`` after both ``uv sync --all-groups`` and ``npm ci``:

    uv run python scripts/third_party_notices.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from importlib.metadata import Distribution, distributions
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
NOTICE_PATH = ROOT / "THIRD-PARTY-NOTICES.md"


@dataclass(frozen=True)
class PackageNotice:
    ecosystem: str
    name: str
    version: str
    licence: str
    attribution: str
    group: str

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.name.lower(), self.version.lower(), self.licence.lower())


def normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    if match is None:
        raise ValueError(f"Cannot parse dependency requirement: {requirement}")
    return normalise_name(match.group(1))


def read_pyproject_dependencies() -> tuple[set[str], set[str]]:
    import tomllib

    data = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = {requirement_name(dep) for dep in data["project"].get("dependencies", [])}
    development = {
        requirement_name(dep) for deps in data.get("dependency-groups", {}).values() for dep in deps
    }
    return runtime, development


def read_package_json_dependencies() -> tuple[set[str], set[str]]:
    data = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    runtime = set(data.get("dependencies", {}))
    development = set(data.get("devDependencies", {}))
    return runtime, development


def metadata_licence(dist: Distribution) -> str:
    metadata = dist.metadata
    value = metadata.get("License-Expression") or ""
    if not value or len(value) > 80:
        classifiers = [
            classifier
            for classifier in metadata.get_all("Classifier", [])
            if classifier.startswith("License ::")
        ]
        if classifiers:
            value = "; ".join(classifier.split("::")[-1].strip() for classifier in classifiers)
    if not value:
        value = (metadata.get("License") or "UNKNOWN")[:80].replace("\n", " ")
    return canonical_licence(value)


def canonical_licence(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, list):
        return " OR ".join(canonical_licence(item) for item in value)
    if isinstance(value, dict):
        return canonical_licence(value.get("type") or value.get("url"))

    text = str(value).strip()
    compact = text.upper().replace(" ", "").replace("-", "")
    known = {
        "APACHESOFTWARELICENSE": "Apache-2.0",
        "APACHELICENSE2.0": "Apache-2.0",
        "APACHE2.0": "Apache-2.0",
        "MITLICENSE": "MIT",
        "BSDLICENSE": "BSD",
        "MOZILLAPUBLICLICENSE2.0(MPL2.0)": "MPL-2.0",
        "MOZILLAPUBLICLICENSE2.0": "MPL-2.0",
        "ISCLICENSE": "ISC",
    }
    if compact in known:
        return known[compact]
    return text or "UNKNOWN"


def project_urls(metadata: Any) -> list[str]:
    urls: list[str] = []
    home_page = metadata.get("Home-page")
    if home_page:
        urls.append(f"Homepage: {home_page}")
    for item in metadata.get_all("Project-URL", []):
        label, _, url = item.partition(",")
        if url.strip() and label.strip().lower() in {"homepage", "source", "repository"}:
            urls.append(f"{label.strip()}: {url.strip()}")
    return sorted(dict.fromkeys(urls))


def copyright_lines(paths: list[Path]) -> list[str]:
    lines: list[str] = []
    skipped_fragments = (
        "above copyright",
        "copyright holder",
        "copyright owner",
        "copyright ownership",
        "copyright doctrines",
        "copyright license",
        "copyright notice",
        "notices of copyright",
        "grant of copyright",
        "[yyyy]",
        "{yyyy}",
    )
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:40_000]
        except OSError:
            continue
        for line in text.splitlines():
            cleaned = re.sub(r"\s+", " ", line.strip(" #/*\t"))
            lowered = cleaned.lower()
            if "copyright" not in lowered:
                continue
            if not lowered.startswith(("copyright", "portions copyright")):
                continue
            if any(fragment in lowered for fragment in skipped_fragments):
                continue
            lines.append(cleaned[:180])
    return sorted(dict.fromkeys(lines))[:3]


def python_copyright_paths(dist: Distribution) -> list[Path]:
    paths: list[Path] = []
    for file in dist.files or []:
        path = Path(str(file))
        lower_name = path.name.lower()
        if lower_name in {"license", "license.txt", "notice", "notice.txt", "copying"}:
            paths.append(Path(dist.locate_file(file)))
        if normalise_name(dist.metadata["Name"]) == "diff-match-patch" and lower_name.endswith(
            ".py"
        ):
            paths.append(Path(dist.locate_file(file)))
    return paths


def python_attribution(dist: Distribution) -> str:
    metadata = dist.metadata
    parts = [f"Copyright: {line}" for line in copyright_lines(python_copyright_paths(dist))]
    parts.extend(project_urls(metadata))
    if not parts:
        author = metadata.get("Author") or metadata.get("Author-email")
        if author:
            parts.append(f"Author: {author}")
    return "; ".join(sorted(dict.fromkeys(parts))) or "Not published in package metadata"


def installed_python_packages() -> list[PackageNotice]:
    runtime, development = read_pyproject_dependencies()
    rows: list[PackageNotice] = []
    for dist in distributions():
        name = dist.metadata["Name"]
        normalised = normalise_name(name)
        if normalised == "palimpsest":
            continue
        if normalised in runtime:
            group = "Direct runtime dependencies"
        elif normalised in development:
            group = "Direct development dependencies"
        else:
            group = "Transitive dependencies"
        rows.append(
            PackageNotice(
                ecosystem="Python",
                name=name,
                version=dist.version,
                licence=metadata_licence(dist),
                attribution=python_attribution(dist),
                group=group,
            )
        )
    return sorted(rows, key=lambda row: row.sort_key)


class NodeModulesMissing(RuntimeError):
    """`frontend/node_modules` is not installed, so there is nothing to audit."""


def npm_tree() -> dict[str, Any]:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise NodeModulesMissing("npm is not on PATH")
    if not (FRONTEND / "node_modules").is_dir():
        raise NodeModulesMissing(f"{FRONTEND / 'node_modules'} does not exist")

    # `npm ls` exits non-zero on any tree problem, including ones irrelevant
    # here such as an unmet optional peer dependency, while still printing the
    # tree. The output is what matters, so parse it and let a genuinely
    # unparseable result be the failure.
    completed = subprocess.run(
        [npm, "ls", "--all", "--json", "--long", "--silent"],
        cwd=FRONTEND,
        check=False,
        capture_output=True,
        text=True,
    )
    if not completed.stdout.strip():
        raise NodeModulesMissing(
            f"npm ls produced no output (exit {completed.returncode}): "
            f"{completed.stderr.strip()[:200]}"
        )
    return json.loads(completed.stdout)


def author_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        name = value.get("name")
        email = value.get("email")
        return " <".join(part for part in (name, email) if part) + (">" if name and email else "")
    return str(value)


def npm_package_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    package_path = Path(path) / "package.json"
    if not package_path.exists():
        return {}
    return json.loads(package_path.read_text(encoding="utf-8"))


def npm_attribution(node: dict[str, Any], package_data: dict[str, Any]) -> str:
    path = node.get("path")
    licence_paths = sorted(Path(path).glob("LICEN*")) if path else []
    parts = [f"Copyright: {line}" for line in copyright_lines(licence_paths)]
    homepage = package_data.get("homepage") or node.get("homepage")
    if homepage:
        parts.append(f"Homepage: {homepage}")
    author = author_text(package_data.get("author"))
    if author and not parts:
        parts.append(f"Author: {author}")
    return "; ".join(sorted(dict.fromkeys(parts))) or "Not published in package metadata"


def collect_npm_nodes(node: dict[str, Any], rows: dict[tuple[str, str], dict[str, Any]]) -> None:
    for name, child in (node.get("dependencies") or {}).items():
        package_name = child.get("name") or name
        version = child.get("version") or "UNKNOWN"
        package_path = Path(child.get("path", "")) / "package.json"
        if package_path.exists():
            rows[(package_name, version)] = child | {"name": package_name}
        collect_npm_nodes(child, rows)


def installed_npm_packages() -> list[PackageNotice]:
    runtime, development = read_package_json_dependencies()
    nodes: dict[tuple[str, str], dict[str, Any]] = {}
    collect_npm_nodes(npm_tree(), nodes)

    rows: list[PackageNotice] = []
    for (name, version), node in sorted(nodes.items()):
        package_data = npm_package_json(node.get("path"))
        if name in runtime:
            group = "Direct runtime dependencies"
        elif name in development:
            group = "Direct development dependencies"
        else:
            group = "Transitive dependencies"
        rows.append(
            PackageNotice(
                ecosystem="npm",
                name=name,
                version=version,
                licence=canonical_licence(node.get("license") or package_data.get("license")),
                attribution=npm_attribution(node, package_data),
                group=group,
            )
        )
    return sorted(rows, key=lambda row: row.sort_key)


def markdown_escape(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")


def render_table(rows: list[PackageNotice]) -> list[str]:
    if not rows:
        return ["No packages in this group.", ""]
    lines = [
        "| Package | Version | Licence | Copyright / homepage |",
        "|---|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(value)
                for value in (row.name, row.version, row.licence, row.attribution)
            )
            + " |"
        )
    lines.append("")
    return lines


def render_notices(rows: list[PackageNotice]) -> str:
    lines = [
        "# Third-party notices",
        "",
        "Generated from the installed Python and npm dependency trees. Re-run with:",
        "",
        "```powershell",
        "cd backend",
        "uv run python scripts/third_party_notices.py",
        "```",
        "",
        "The project itself is Apache-2.0; this file records third-party packages only.",
        "",
    ]

    for ecosystem in ("Python", "npm"):
        lines.extend([f"## {ecosystem}", ""])
        ecosystem_rows = [row for row in rows if row.ecosystem == ecosystem]
        for group in (
            "Direct runtime dependencies",
            "Direct development dependencies",
            "Transitive dependencies",
        ):
            lines.extend([f"### {group}", ""])
            lines.extend(render_table([row for row in ecosystem_rows if row.group == group]))

    unknown = sorted(
        (row for row in rows if row.licence == "UNKNOWN" or "UNKNOWN" in row.licence),
        key=lambda row: (row.ecosystem, row.sort_key),
    )
    lines.extend(["## Licence metadata gaps", ""])
    if unknown:
        for row in unknown:
            lines.append(f"- {row.ecosystem}: {row.name} {row.version}")
    else:
        lines.append("No package currently has an unknown licence in its installed metadata.")
    lines.append("")
    return "\n".join(lines)


def generate() -> str:
    return render_notices([*installed_python_packages(), *installed_npm_packages()])


def main() -> int:
    NOTICE_PATH.write_text(generate(), encoding="utf-8", newline="\n")
    print(f"Wrote {NOTICE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
