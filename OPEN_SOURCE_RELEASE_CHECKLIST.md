# Open-source release checklist

`palimpsest` stays private until every item below has been reviewed by the
owner. The automated checks reduce the search space; they do not replace the
manual review.

## 1. Review what will become public

- [ ] Read the repository as a stranger: `README`, user guide, architecture,
      governance files, issue forms, and pull-request template.
- [ ] Review the complete commit history, not only `main`'s current tree.
- [ ] Confirm all author identities shown by
      `python scripts/public_release_audit.py` are intended to become public.
      The current set is two human identities plus `dependabot[bot]`.
- [ ] Confirm the personal enforcement address in `CODE_OF_CONDUCT.md` is the
      address you want published.
- [ ] Confirm the three screenshots contain no personal data, private
      manuscripts, browser profile information, or internal host names.
- [ ] Confirm every sample text is public domain or project-authored.
- [ ] Review `NOTICE`, `THIRD-PARTY-NOTICES.md`, and ADR-0008.
- [x] Confirm no lockfile resolves from a private index. `backend/uv.lock` and
      `docs-site/uv.lock` now resolve from `https://pypi.org/simple`, and
      `frontend/package-lock.json` from `registry.npmjs.org`. The **Lockfiles**
      CI job and `scripts/check_lockfile_indexes.py` keep it that way; use the
      **Relock** workflow to regenerate them.
- [ ] Decide whether the private-index URLs that remain in *history* are
      acceptable. They are proxy URLs for public packages rather than
      credentials, and removing them means rewriting every commit. The audit
      prints the current count.

Run the repeatable history audit:

```bash
python scripts/public_release_audit.py --require-clean
```

The script does not print matched secret values. It checks every commit for
secret-shaped content, risky filenames, absolute user paths, forbidden commit
trailers, and blobs over 1 MB. It also prints the identities and internal-feed
URL counts that need a human decision.

## 2. Resolve outstanding automation

- [x] Triage every open Dependabot pull request. Do not merge major updates
      merely because their checks pass.
- [x] Confirm CI is green on Python 3.12 and 3.13, frontend, schema contract,
      and end-to-end jobs.
- [x] Run the **Docs** workflow manually and inspect the built artifact.
- [x] Run **Public release readiness** manually and retain the green run.
- [x] Confirm CodeQL is skipped only because the repository is private.

## 3. Change visibility

Changing visibility is intentionally not automated by this repository.

- [ ] Change the repository from **Private** to **Public** in GitHub settings.
- [ ] Verify the repository as a logged-out visitor.
- [ ] Clone it into a machine/account with no private-index configuration and
      run the documented setup. This is the only honest external-contributor
      smoke test.

## 4. Turn on public-repository protections

- [ ] Add a `main` ruleset requiring pull requests and the seven CI checks.
- [ ] Require branches to be up to date before merge.
- [ ] Enable private vulnerability reporting.
- [ ] Enable secret scanning and push protection.
- [ ] Confirm Dependabot alerts and security updates are enabled.
- [ ] Confirm CodeQL now runs instead of skipping and review its first result.
- [ ] Enable GitHub Pages with **GitHub Actions** as the source, run **Docs**,
      and verify the published guide, Mermaid diagrams, search, and screenshots.
- [ ] Set the repository homepage to the published guide.
- [x] Add repository topics such as `digital-humanities`,
      `textual-criticism`, `diff`, `tei`, and `fastapi`.

Already applied while private: squash-only merges, reasoning from the
pull-request description in the squash commit, automatic deletion of merged
branches, issues enabled, and unused Projects/Wiki surfaces disabled.

The repository includes a repeatable installer for the branch and security
settings above:

```bash
python scripts/configure_public_repository.py
python scripts/configure_public_repository.py --apply
```

The first command is a dry run. While the repository is private it explains
the GitHub-plan blocker and changes nothing. After visibility becomes public,
`--apply` requires pull requests and the seven CI checks, blocks force pushes
and branch deletion (including for administrators), requires up-to-date
branches and resolved conversations, and enables vulnerability reporting,
Dependabot security updates, secret scanning, and push protection.

The default is zero required approvals because this is currently a
solo-maintainer repository. Use `--required-approvals 1` when another
maintainer can review changes.

## 5. Publish 0.1.0

- [ ] Add your ORCID to `CITATION.cff` and to `.zenodo.json`, so the archived
      record and every later citation resolve to you rather than to a name.
- [ ] Enable the Zenodo–GitHub integration **before** tagging: Zenodo archives
      on the release webhook, so enabling it afterwards does nothing for this
      release. `.zenodo.json` supplies the record's metadata.
- [ ] Replace `Unreleased` with the release date in `CHANGELOG.md`.
- [ ] Confirm `0.1.0` in both package manifests.
- [ ] Tag the reviewed commit `v0.1.0`.
- [ ] Create a GitHub Release from the changelog entry.
- [ ] Add the Zenodo **concept** DOI — the one that always resolves to the
      latest version — to `CITATION.cff` as `doi:`, set `date-released:`, and
      add a DOI badge to `README.md`.
- [ ] Submit the Zenodo record to the `digital-humanities` community.
- [ ] Verify the source archive contains `LICENSE`, `NOTICE`,
      `THIRD-PARTY-NOTICES.md`, `CITATION.cff`, governance files, and the
      documentation source.

Publishing to PyPI, npm, or a container registry is a separate decision and is
not required for the source release.
