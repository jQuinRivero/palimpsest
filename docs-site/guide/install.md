# Install and run

The backend is managed with `uv`; the frontend is managed with npm. These commands are run from the repository root.

## Requirements

- Python 3.12 or newer. `uv` can provision the interpreter.
- Node.js. The frontend package is verified with `npm ci`.

## Install dependencies

```bash
uv --directory backend sync --all-groups
npm --prefix frontend ci
```

## Run the API

```bash
uv --directory backend run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API serves `/api/v1/health`, `/api/v1/capabilities`, document upload, comparison creation, block paging, and TEI export.

## Run the web app

In a second shell:

```bash
npm --prefix frontend run dev
```

The Next.js app serves the uploader at <http://localhost:3000>. The API runs at <http://127.0.0.1:8000>.

## Useful checks

```bash
uv --directory backend run pytest
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run gen:types
npm --prefix frontend run check:types-drift
```

The TypeScript API types are generated from the backend OpenAPI schema and
committed; `check:types-drift` fails when the committed mirror is stale. Both
type-generation commands require the API to be running on port 8000. With it
stopped, they fail with `Could not read the OpenAPI schema` and an
`ECONNREFUSED 127.0.0.1:8000` cause.
