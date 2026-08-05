"""Document upload and retrieval."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.deps import get_registry, get_store
from app.api.errors import ApiError
from app.config import Settings, get_settings
from app.models.api import ErrorCode
from app.models.document import Document, DocumentSummary
from app.models.identifiers import new_document_id
from app.services.ingestion.base import (
    DocumentSource,
    SourceProbe,
    SourceTooLargeError,
)
from app.services.ingestion.pdf import ScannedDocumentError
from app.services.ingestion.registry import ParserRegistry, UnsupportedFormatError
from app.storage.store import DocumentNotFound, SessionStore

router = APIRouter(prefix="/documents", tags=["documents"])

#: Enough of the file to sniff container contents, not merely the first magic
#: number. A DOCX and an XLSX share the ZIP signature, so telling them apart
#: means finding `word/document.xml` among the archive's entry names — which
#: sits well past the first few bytes. The whole upload is already in memory,
#: so a generous prefix costs nothing.
_MAGIC_BYTES = 8192


async def _read_capped(upload: UploadFile, limit: int) -> bytes:
    """Read the upload, refusing anything over ``limit``.

    ``Content-Length`` is client-supplied and can lie, so the streamed bytes
    are counted as they arrive rather than trusted from the header.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        if total > limit:
            raise ApiError(
                ErrorCode.FILE_TOO_LARGE,
                f"Upload exceeds the {limit} byte limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
    registry: ParserRegistry = Depends(get_registry),
    store: SessionStore = Depends(get_store),
) -> DocumentSummary:
    data = await _read_capped(file, settings.max_upload_bytes)

    if not data.strip():
        raise ApiError(ErrorCode.EMPTY_DOCUMENT, "The uploaded witness is empty.")

    probe = SourceProbe(
        filename=file.filename,
        media_type=file.content_type,
        magic_bytes=data[:_MAGIC_BYTES],
        size_bytes=len(data),
    )

    try:
        parser_class = registry.resolve(probe)
    except UnsupportedFormatError as exc:
        raise ApiError(ErrorCode.UNSUPPORTED_FORMAT, str(exc)) from exc

    source = DocumentSource(
        filename=file.filename,
        media_type=file.content_type,
        size_bytes=len(data),
        data=data,
        max_decompressed_bytes=settings.max_decompressed_bytes,
        max_pages=settings.max_pdf_pages,
    )

    try:
        document = parser_class().parse(source)
    except ApiError:
        raise
    except SourceTooLargeError as exc:
        # Well-formed, and simply more than we are willing to spend. That is a
        # different answer from "malformed", and 413 is the honest one: the
        # file is too large — once unpacked.
        raise ApiError(ErrorCode.FILE_TOO_LARGE, str(exc)) from exc
    except ScannedDocumentError as exc:
        # A deliberate, honest failure: the file is a scan and OCR does not
        # ship in v1. Returning an empty document would be a silent lie about
        # a file the researcher can plainly read.
        raise ApiError(ErrorCode.OCR_REQUIRED, str(exc)) from exc
    except Exception as exc:
        raise ApiError(
            ErrorCode.MALFORMED_DOCUMENT,
            f"The witness could not be parsed: {exc}",
        ) from exc

    if not document.blocks:
        raise ApiError(
            ErrorCode.EMPTY_DOCUMENT,
            "The witness contained no readable text.",
        )

    # The id is assigned here, never by the parser. It is the whole
    # access-control model in v1, so it must come from one audited source with
    # 128 bits of entropy — and a parser that returned a constant would
    # silently overwrite every previous upload of that format.
    updates: dict[str, object] = {"id": new_document_id()}
    if title:
        updates["title"] = title
    document = document.model_copy(update=updates)

    expires_at = datetime.now(UTC) + timedelta(hours=settings.document_ttl_hours)
    return store.put_document(document, size_bytes=len(data), expires_at=expires_at)


@router.get("/{document_id}", response_model=Document)
def get_document(
    document_id: str,
    store: SessionStore = Depends(get_store),
) -> Document:
    try:
        return store.get_document(document_id)
    except DocumentNotFound as exc:
        raise ApiError(
            ErrorCode.DOCUMENT_NOT_FOUND,
            f"No live document with id {document_id}.",
        ) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    store: SessionStore = Depends(get_store),
) -> None:
    store.delete_document(document_id)
