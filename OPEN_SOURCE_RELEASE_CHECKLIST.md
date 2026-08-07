# Open-source release checklist

`palimpsest` stays private until every item below has been reviewed by the
owner. The automated checks reduce the search space; they do not replace the
manual review.

## 1. Review what will become public

- [ ] Read the repository as a stranger: `README`, user guide, architecture,
      governance files, issue forms, and pull-request template.
- [ ] Review the complete commit history, not only `main`'s current tree.
- [ ] Confirm both author identities shown by
      `python scripts/public_release_audit.py` are intended to become public.
- [ ] Confirm the personal enforcement address in `CODE_OF_CONDUCT.md` is the
      address you want published.
- [ ] Confirm the three screenshots contain no personal data, private
      manuscripts, browser profile information, or internal host names.
- [ ] Confirm every sample text is public domain or project-authored.
- [ ] Review `NOTICE`, `THIRD-PARTY-NOTICES.md`, and ADR-0008.
- [ ] Decide whether the CFS URLs in `backend/uv.lock` and `docs-site/uv.lock`
      are acceptable in the public repository. They are required on the
      managed development devices and are intentionally **not** rewritten to
      public PyPI URLs.

Run the repeatable history audit:

```bash
python scripts/public_release_audit.py --require-clean
```

The script does not print matched secret values. It checks every commit for
secret-shaped content, risky filenames, absolute user paths, forbidden commit
trailers, and blobs over 1 MB. It also prints the identities and internal-feed
URL counts that need a human decision.

## 2. Resolve outstanding automation

- [ ] Triage every open Dependabot pull request. Do not merge major updates
      merely because their checks pass.
- [ ] Confirm CI is green on Python 3.12 and 3.13, frontend, schema contract,
      and end-to-end jobs.
- [ ] Run the **Docs** workflow manually and inspect the built artifact.
- [ ] Run **Public release readiness** manually and retain the green run.
- [ ] Confirm CodeQL is skipped only because the repository is private.

## 3. Change visibility

Changing visibility is intentionally not automated by this repository.

- [ ] Change the repository from **Private** to **Public** in GitHub settings.
- [ ] Verify the repository as a logged-out visitor.
- [ ] Clone it into a machine/account without Microsoft feed configuration and
      run the documented setup. This is the only honest external-contributor
      smoke test.

## 4. Turn on public-repository protections

- [ ] Add a `main` ruleset requiring pull requests and the five CI checks.
- [ ] Require branches to be up to date before merge.
- [ ] Enable private vulnerability reporting.
- [ ] Enable secret scanning and push protection.
- [ ] Confirm Dependabot alerts and security updates are enabled.
- [ ] Confirm CodeQL now runs instead of skipping and review its first result.
- [ ] Enable GitHub Pages with **GitHub Actions** as the source, run **Docs**,
      and verify the published guide, Mermaid diagrams, search, and screenshots.
- [ ] Set the repository homepage to the published guide.
- [ ] Add repository topics such as `digital-humanities`,
      `textual-criticism`, `diff`, `tei`, and `fastapi`.

## 5. Publish 0.1.0

- [ ] Replace `Unreleased` with the release date in `CHANGELOG.md`.
- [ ] Confirm `0.1.0` in both package manifests.
- [ ] Tag the reviewed commit `v0.1.0`.
- [ ] Create a GitHub Release from the changelog entry.
- [ ] Verify the source archive contains `LICENSE`, `NOTICE`,
      `THIRD-PARTY-NOTICES.md`, governance files, and the documentation source.

Publishing to PyPI, npm, or a container registry is a separate decision and is
not required for the source release.
