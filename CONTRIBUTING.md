# Contributing to palimpsest

Thank you for helping make `palimpsest` a better tool for close reading. This repository is Apache-2.0-licensed open source maintained by `@jQuinRivero`.

## Start with the specification

The documents under [`docs/`](docs/) are the normative specification. If code and spec disagree, treat that as a defect in one of them and resolve it explicitly in the change. Do not let behavior drift silently.

Architectural changes go through an ADR. See [`docs/adr/README.md`](docs/adr/README.md) for numbering, status, and template conventions.

## Development environment

Use Python 3.12+ with `uv`, and Node 20+ for the frontend. CI currently exercises Python 3.12 and 3.13, and Node 24.

Install backend dependencies:

```bash
cd backend
uv sync --all-groups --frozen
```

Run the API locally:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Install frontend dependencies with `npm ci`, never `npm install`:

```bash
cd frontend
npm ci
```

Run the web app locally:

```bash
cd frontend
npm run dev
```

Backend commands that execute project code should go through `uv run`, so they use the locked environment rather than whatever Python happens to be on PATH.

## Lockfiles

Both lockfiles must resolve from canonical public indexes: `backend/uv.lock`
and `docs-site/uv.lock` from `https://pypi.org/simple`, and
`frontend/package-lock.json` from `registry.npmjs.org`. CI enforces this in the
**Lockfiles** job via `scripts/check_lockfile_indexes.py`.

This matters more than it looks. A lockfile records whichever index resolved
it, so regenerating one behind a corporate proxy, mirror, or private registry
bakes that host into a file everyone installs from. `uv sync --frozen` fetches
the URLs a lock names *verbatim* and ignores index configuration, so a lock
pointing at a private host cannot be corrected at install time — it simply
fails for everyone who cannot reach it.

### Regenerating `backend/uv.lock` or `docs-site/uv.lock`

Do not run `uv lock` locally and commit the result unless you know your machine
resolves directly from PyPI. Instead run the **Relock** workflow
(`.github/workflows/relock.yml`) from the Actions tab. It resolves on a runner
with direct PyPI access, verifies the output, and opens a pull request. Use its
`upgrade` input to move dependencies rather than merely re-pinning them.

Never hand-edit resolved URLs. Canonical PyPI paths are content-addressed, so a
correct URL cannot be constructed by search and replace.

### Regenerating `frontend/package-lock.json`

`frontend/package-lock.json` is generated on Linux so it contains the optional
packages Linux CI needs. On Windows, `npm install` can silently rewrite it into
a platform-local state that installs for you and fails in CI. Use `npm ci` for
ordinary work.

When it really must be regenerated, do it deliberately from `frontend`. On
macOS or Linux:

```bash
docker run --rm -v "$PWD:/w" -w /w node:24 npm install --package-lock-only
```

On PowerShell:

```powershell
docker run --rm -v "${PWD}:/w" -w /w node:24 npm install --package-lock-only
```

Before committing, confirm every `resolved` host is `registry.npmjs.org`.

### Working behind a private index

If your machine can only reach PyPI through a proxy, configure that locally
rather than in anything committed. uv reads a `uv.toml` from the project
directory, which is gitignored here for exactly this purpose:

```toml
# uv.toml — local only, never committed
[[index]]
url = "https://your-proxy.example/pypi/simple"
default = true
```

Project-level `uv.toml` takes precedence over `pyproject.toml`, and
`UV_DEFAULT_INDEX` overrides both. Use plain `uv sync` rather than
`uv sync --frozen` in that setup, since `--frozen` bypasses index configuration
entirely.

## Tests and checks

Backend:

```bash
cd backend
uv run pytest
```

Frontend:

```bash
cd frontend
npx playwright install chromium
npm run typecheck
npm run lint
npm run test:e2e
```

The Playwright browser install is a one-time local setup step before `npm run test:e2e`.

The end-to-end suite starts its own API and web server. It also reuses an API already listening on port 8000, which is useful while iterating but wrong if that API was started with the ordinary development command above. The ordinary server uses production limits; the windowing tests need deliberately lowered limits. The setup project at `frontend/e2e/api-config.setup.ts` detects that mismatch before the suite runs and tells you to stop the hand-started API.

If API models change, regenerate and check the committed TypeScript types while the backend is running on port 8000:

```bash
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another shell:

```bash
cd frontend
npm run gen:types
npm run check:types-drift
```

Both type-generation commands fetch `http://127.0.0.1:8000/api/v1/openapi.json`. If the API is not running, they fail with `Could not read the OpenAPI schema` and `connect ECONNREFUSED 127.0.0.1:8000`, followed by the reminder to start the backend first.

## Commits and pull requests

Use conventional-commit prefixes already used in the history:

- `feat`
- `fix`
- `docs`
- `test`
- `ci`
- `build`
- `refactor`
- `chore`

Commit messages in this repository explain why the change exists, not only what changed. Prefer a concise subject and prose body that records the reasoning, tradeoff, or failure mode that made the change necessary.

Pull requests should link the issue, describe the reason for the change, list the checks run, and say whether the normative spec in `docs/` needed an update.
