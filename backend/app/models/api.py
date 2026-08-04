"""API request and response models, and the error taxonomy.

See docs/06-api-reference.md. Errors are RFC 9457 ``application/problem+json``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.diff import DiffOptions
from app.models.document import SourceFormat


class ErrorCode(StrEnum):
    """Every error the API can return.

    Each maps to one HTTP status via ``ERROR_STATUS``.
    """

    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    MALFORMED_DOCUMENT = "MALFORMED_DOCUMENT"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    COMPARISON_NOT_FOUND = "COMPARISON_NOT_FOUND"
    COMPARISON_EXPIRED = "COMPARISON_EXPIRED"
    DIFF_BUDGET_EXCEEDED = "DIFF_BUDGET_EXCEEDED"
    #: A deliberate, honest failure in v1: a scanned PDF yields no text, and
    #: returning an empty document would be a silent lie.
    OCR_REQUIRED = "OCR_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNSUPPORTED_FORMAT: 415,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.MALFORMED_DOCUMENT: 422,
    ErrorCode.EMPTY_DOCUMENT: 422,
    ErrorCode.DOCUMENT_NOT_FOUND: 404,
    ErrorCode.COMPARISON_NOT_FOUND: 404,
    #: 410 rather than 404: the resource existed and is knowably gone, which
    #: tells the client not to retry.
    ErrorCode.COMPARISON_EXPIRED: 410,
    ErrorCode.DIFF_BUDGET_EXCEEDED: 413,
    ErrorCode.OCR_REQUIRED: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
}

ERROR_TITLE: dict[ErrorCode, str] = {
    ErrorCode.UNSUPPORTED_FORMAT: "Unsupported document format",
    ErrorCode.FILE_TOO_LARGE: "File too large",
    ErrorCode.MALFORMED_DOCUMENT: "Malformed document",
    ErrorCode.EMPTY_DOCUMENT: "Empty document",
    ErrorCode.DOCUMENT_NOT_FOUND: "Document not found",
    ErrorCode.COMPARISON_NOT_FOUND: "Comparison not found",
    ErrorCode.COMPARISON_EXPIRED: "Comparison expired",
    ErrorCode.DIFF_BUDGET_EXCEEDED: "Comparison too large",
    ErrorCode.OCR_REQUIRED: "Document requires OCR",
    ErrorCode.RATE_LIMITED: "Too many requests",
    ErrorCode.INTERNAL_ERROR: "Internal error",
}


class ProblemDetail(BaseModel):
    """RFC 9457 problem detail."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: ErrorCode


class CreateComparisonRequest(BaseModel):
    a_document_id: str
    b_document_id: str
    options: DiffOptions = Field(default_factory=DiffOptions)


class ComparisonStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ComparisonAccepted(BaseModel):
    """Returned with 202 when a comparison exceeds the inline diff budget.

    The client polls ``GET /comparisons/{id}`` and receives this same shape
    until the comparison reaches ``COMPLETE``, at which point the full
    ``ComparisonResult`` is returned instead.
    """

    comparison_id: str
    status: ComparisonStatus = ComparisonStatus.PENDING
    created_at: datetime
    expires_at: datetime
    #: Seconds the client should wait before polling again.
    retry_after: int = 2


class ParserCapabilitiesResponse(BaseModel):
    name: str
    version: str
    source_format: SourceFormat
    extensions: list[str]
    media_types: list[str]
    preserves_headings: bool
    preserves_page_numbers: bool
    is_lossy: bool
    is_async: bool
    requires_network: bool
    emits_confidence: bool
    emits_bboxes: bool


class CapabilitiesResponse(BaseModel):
    """What this server can parse, and its current limits.

    The client builds its upload accept list from this rather than hardcoding
    formats, which is what makes registering the OCR parser later a
    zero-frontend-change event.
    """

    parsers: list[ParserCapabilitiesResponse]
    max_upload_bytes: int
    max_blocks_per_comparison: int
    max_tokens_per_comparison: int
    default_block_page_limit: int
    max_block_page_limit: int
    diff_options_defaults: DiffOptions


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
