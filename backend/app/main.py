"""FastAPI application entry point.

Run with: ``uv run uvicorn app.main:app --reload``
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import ApiError, api_error_handler, unhandled_error_handler
from app.api.v1 import comparisons, documents, meta
from app.config import get_settings
from app.models.api import ProblemDetail

API_PREFIX = "/api/v1"

#: Declared on every router so the generated OpenAPI schema documents the
#: RFC 9457 error shape. Without this the client's generated types have no
#: ProblemDetail and cannot branch on an error code.
PROBLEM_RESPONSES: dict[int | str, dict[str, object]] = {
    400: {"model": ProblemDetail, "description": "Bad request"},
    404: {"model": ProblemDetail, "description": "Not found"},
    410: {"model": ProblemDetail, "description": "Gone"},
    413: {"model": ProblemDetail, "description": "Payload too large"},
    415: {"model": ProblemDetail, "description": "Unsupported media type"},
    422: {"model": ProblemDetail, "description": "Unprocessable content"},
    429: {"model": ProblemDetail, "description": "Too many requests"},
    500: {"model": ProblemDetail, "description": "Internal error"},
}


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="palimpsest",
        version=settings.version,
        description="Read the difference between two versions of a literary text.",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url="/docs",
    )

    # Development runs uvicorn and next dev on separate ports.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(meta.router, prefix=API_PREFIX)
    app.include_router(documents.router, prefix=API_PREFIX, responses=PROBLEM_RESPONSES)
    app.include_router(comparisons.router, prefix=API_PREFIX, responses=PROBLEM_RESPONSES)

    return app


app = create_app()
