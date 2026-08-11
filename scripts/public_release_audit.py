"""Audit the repository and its history before changing visibility to public.

The script deliberately prints categories, paths, and counts — never matching
secret values. It is a release gate, not a secret exfiltration tool.
"""

from __future__ import annotations

import argparse
import locale
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BLOB_BYTES = 1_000_000

REQUIRED_FILES = (
    "LICENSE",
    "NOTICE",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "THIRD-PARTY-NOTICES.md",
    "CITATION.cff",
    ".github/CODEOWNERS",
)

RISKY_NAMES = {
    ".env",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "secrets.json",
    "tokens.json",
}
RISKY_SUFFIXES = {".db", ".key", ".pem", ".pfx", ".sqlite"}

SECRET_PATTERNS = {
    "private key": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "GitHub token": re.compile(
        r"(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})"
    ),
    "JWT": re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "assigned secret": re.compile(
        r"""(?ix)
        (?:api[_-]?key|client[_-]?secret|password|passwd|
           connection[_-]?string|access[_-]?token)
        \s*[:=]\s*["'][^"']{8,}
        """
    ),
}

PERSONAL_PATHS = re.compile(
    r"(?i)(?:[A-Z]:\\Users\\[^\\\s]+|/Users/[^/\s]+|/home/[^/\s]+)"
)
COPILOT_TRAILER = re.compile(r"(?im)^(?:Co-authored-by:\s*Copilot|Copilot-Session:)")


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


def git(*args: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
        input=input_text,
    )
    return completed.stdout


def tracked_files() -> list[str]:
    return [line for line in git("ls-files").splitlines() if line]


def names_ever_committed() -> list[str]:
    output = git("log", "--all", "--name-only", "--pretty=format:")
    return sorted({line for line in output.splitlines() if line})


def history_patch() -> str:
    # The scanner's own regex source necessarily contains the strings it is
    # looking for (for example ``/Users/`` and ``/home/``). Excluding only this
    # file avoids a self-match; every other path and every commit remains in
    # scope.
    return git(
        "log",
        "--all",
        "-p",
        "--no-color",
        "--format=commit:%H",
        "--",
        ".",
        ":!scripts/public_release_audit.py",
    )


def largest_blobs() -> list[tuple[int, str]]:
    objects = git("rev-list", "--objects", "--all")
    checked = git(
        "cat-file",
        "--batch-check=%(objecttype) %(objectsize) %(rest)",
        input_text=objects,
    )
    rows: list[tuple[int, str]] = []
    for line in checked.splitlines():
        parts = line.split(" ", maxsplit=2)
        if len(parts) != 3:
            continue
        kind, size, path = parts
        if kind == "blob" and path:
            rows.append((int(size), path))
    return sorted(rows, reverse=True)


def risky_path(path: str) -> bool:
    name = Path(path).name.lower()
    return name in RISKY_NAMES or Path(name).suffix in RISKY_SUFFIXES


def audit(*, require_clean: bool) -> list[Finding]:
    findings: list[Finding] = []

    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        findings.append(
            Finding("FAIL", f"required public files missing: {', '.join(missing)}")
        )
    else:
        findings.append(
            Finding("PASS", f"all {len(REQUIRED_FILES)} public files are present")
        )

    risky = [path for path in names_ever_committed() if risky_path(path)]
    if risky:
        findings.append(
            Finding("FAIL", f"risky filenames appear in history: {', '.join(risky)}")
        )
    else:
        findings.append(
            Finding(
                "PASS", "no credential, key, database, or .env filenames in history"
            )
        )

    patch = history_patch()
    for label, pattern in SECRET_PATTERNS.items():
        count = len(pattern.findall(patch))
        findings.append(
            Finding(
                "FAIL" if count else "PASS",
                f"{label} patterns in full history: {count}",
            )
        )

    personal_paths = len(PERSONAL_PATHS.findall(patch))
    findings.append(
        Finding(
            "FAIL" if personal_paths else "PASS",
            f"absolute user-profile paths in full history: {personal_paths}",
        )
    )

    trailers = len(COPILOT_TRAILER.findall(git("log", "--all", "--format=%B")))
    findings.append(
        Finding(
            "FAIL" if trailers else "PASS",
            f"forbidden Copilot commit trailers: {trailers}",
        )
    )

    oversized = [
        (size, path) for size, path in largest_blobs() if size > MAX_BLOB_BYTES
    ]
    if oversized:
        summary = ", ".join(f"{path} ({size:,} bytes)" for size, path in oversized)
        findings.append(
            Finding("FAIL", f"blobs over {MAX_BLOB_BYTES:,} bytes: {summary}")
        )
    else:
        findings.append(
            Finding("PASS", f"no blob in history exceeds {MAX_BLOB_BYTES:,} bytes")
        )

    identities = sorted(
        set(
            git(
                "log",
                "--all",
                "--encoding=UTF-8",
                "--format=%an <%ae>",
            ).splitlines()
        )
    )
    findings.append(
        Finding(
            "INFO",
            "author identities that become public: " + "; ".join(identities),
        )
    )

    for lock in ("backend/uv.lock", "docs-site/uv.lock", "frontend/package-lock.json"):
        path = ROOT / lock
        internal = (
            path.read_text(encoding="utf-8").count("pkgs.visualstudio.com")
            if path.is_file()
            else 0
        )
        findings.append(Finding("INFO", f"{lock}: {internal} internal-feed URLs"))

    if require_clean:
        changes = git("status", "--porcelain").splitlines()
        findings.append(
            Finding(
                "FAIL" if changes else "PASS",
                f"working tree changes: {len(changes)}",
            )
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="fail when the working tree has staged, unstaged, or untracked files",
    )
    args = parser.parse_args()

    findings = audit(require_clean=args.require_clean)
    for finding in findings:
        print(f"[{finding.level}] {finding.message}")

    failures = sum(finding.level == "FAIL" for finding in findings)
    print(f"\nPublic-release audit: {failures} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
