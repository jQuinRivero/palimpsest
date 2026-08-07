# Contributing to palimpsest

Thank you for helping make `palimpsest` a better tool for close reading. This repository is personal, Apache-2.0-licensed open source by `@jQuinRivero`; it is not a Microsoft project.

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

## The frontend lockfile

`frontend/package-lock.json` is generated on Linux so it contains optional packages that Linux CI needs. On Windows, `npm install` can silently rewrite the lockfile into a platform-local state that installs for you and fails in CI. Use `npm ci` for ordinary work.

When the lockfile really must be regenerated, do it deliberately from `frontend`. On macOS or Linux:

```bash
docker run --rm -v "$PWD:/w" -w /w node:24 npm install --package-lock-only
```

On PowerShell:

```powershell
docker run --rm -v "${PWD}:/w" -w /w node:24 npm install --package-lock-only
```

Before committing the regenerated lockfile, rewrite any `redacted.invalid` resolved hosts back to `registry.npmjs.org`. Those feed URLs are machine-specific mirrors; the public lockfile should stay registry-canonical.

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
