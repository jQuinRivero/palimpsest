"""Apply the GitHub protections that become available after public release.

The repository is currently private on a plan where branch protection and
rulesets return HTTP 403. This script refuses to make a partial configuration:
run it only after the owner has completed OPEN_SOURCE_RELEASE_CHECKLIST.md and
changed visibility to public.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

REPOSITORY = "jQuinRivero/palimpsest"
MAIN_BRANCH = "main"
REQUIRED_CHECKS = (
    "Lockfiles",
    "Backend (py3.12)",
    "Backend (py3.13)",
    "Frontend",
    "Schema contract",
    "End-to-end",
    "Container images",
)


def gh(*args: str, input_json: dict[str, Any] | None = None) -> str:
    """Run gh and return stdout, preserving its useful error message."""
    completed = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        input=json.dumps(input_json) if input_json is not None else None,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout


def visibility() -> str:
    output = gh(
        "repo", "view", REPOSITORY, "--json", "visibility", "--jq", ".visibility"
    )
    return output.strip()


def protection_payload(required_approvals: int) -> dict[str, Any]:
    """The main-branch policy for a solo-maintainer open-source project."""
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": list(REQUIRED_CHECKS),
        },
        "enforce_admins": True,
        # A count of zero still requires changes to arrive through a pull
        # request, without making a solo maintainer find someone else to
        # approve their own work. Raise it when there is another maintainer.
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "require_last_push_approval": False,
            "required_approving_review_count": required_approvals,
        },
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }


def apply(required_approvals: int) -> None:
    endpoint = f"repos/{REPOSITORY}/branches/{MAIN_BRANCH}/protection"
    gh(
        "api",
        "--method",
        "PUT",
        endpoint,
        "--input",
        "-",
        input_json=protection_payload(required_approvals),
    )

    # Public repositories get these features without GitHub Advanced Security.
    gh("api", "--method", "PUT", f"repos/{REPOSITORY}/private-vulnerability-reporting")
    gh("api", "--method", "PUT", f"repos/{REPOSITORY}/vulnerability-alerts")
    gh("api", "--method", "PUT", f"repos/{REPOSITORY}/automated-security-fixes")
    gh(
        "repo",
        "edit",
        REPOSITORY,
        "--enable-secret-scanning",
        "--enable-secret-scanning-push-protection",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the policy; without this flag, print the plan only",
    )
    parser.add_argument(
        "--required-approvals",
        type=int,
        choices=range(7),
        default=0,
        metavar="0..6",
        help="approvals required per PR (default: 0 for a solo maintainer)",
    )
    args = parser.parse_args()

    current_visibility = visibility()
    print(f"Repository: {REPOSITORY} ({current_visibility})")
    print(f"Protected branch: {MAIN_BRANCH}")
    print(f"Required checks: {', '.join(REQUIRED_CHECKS)}")
    print(f"Required approvals: {args.required_approvals}")
    print("Enforced: PRs, up-to-date checks, linear history, resolved conversations")
    print("Blocked: admin bypass, force pushes, branch deletion")
    print(
        "Security: private reporting, alerts, security updates, secret push protection"
    )

    if current_visibility != "PUBLIC":
        print(
            "\nNot applied: GitHub returns HTTP 403 for branch protection on this "
            "private repository under the current plan. Complete the manual "
            "review, change visibility to public, then run this command again."
        )
        return 2 if args.apply else 0

    if not args.apply:
        print("\nDry run only. Add --apply to configure GitHub.")
        return 0

    try:
        apply(args.required_approvals)
    except RuntimeError as exc:
        print(f"\nConfiguration failed: {exc}", file=sys.stderr)
        return 1

    print("\nPublic repository protections applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
