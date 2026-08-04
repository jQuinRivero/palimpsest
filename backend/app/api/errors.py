"""RFC 9457 problem responses and the exception types the API maps to them."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.models.api import ERROR_STATUS, ERROR_TITLE, ErrorCode, ProblemDetail

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ApiError(Exception):
    """An error with a defined code, rendered as ``application/problem+json``."""

    def __init__(self, code: ErrorCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)

    @property
    def status(self) -> int:
        return ERROR_STATUS[self.code]

    def to_problem(self) -> ProblemDetail:
        return ProblemDetail(
            type=f"https://palimpsest.dev/problems/{self.code.value.lower()}",
            title=ERROR_TITLE[self.code],
            status=self.status,
            detail=self.detail,
            code=self.code,
        )

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status,
            content=self.to_problem().model_dump(mode="json"),
            media_type=PROBLEM_MEDIA_TYPE,
        )


async def api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return exc.to_response()


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Never leak an internal traceback to a client; the detail is deliberately
    # generic and the real error is logged.
    return ApiError(ErrorCode.INTERNAL_ERROR, "An unexpected error occurred.").to_response()
