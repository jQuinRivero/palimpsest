# Install and run

The backend is managed with `uv`; the frontend is managed with npm. These commands are run from the repository root.

## Requirements

- Python 3.12 or newer. `uv` can provision the interpreter.
- Node.js. The frontend package is verified with `npm ci`.

## Install dependencies

```powershell
uv --directory backend sync --all-groups
npm --prefix frontend ci
```

## Run the API

```powershell
uv --directory backend run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API serves `/api/v1/health`, `/api/v1/capabilities`, document upload, comparison creation, block paging, and TEI export.

## Run the web app

In a second shell:

```powershell
npm --prefix frontend run dev
```

The Next.js app serves the uploader at <http://localhost:3000>. The API runs at <http://127.0.0.1:8000>.

## Useful checks

```powershell
uv --directory backend run pytest
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run gen:types
npm --prefix frontend run check:types-drift
```

The TypeScript API types are generated from the backend OpenAPI schema and committed; `check:types-drift` fails when the committed mirror is stale.
