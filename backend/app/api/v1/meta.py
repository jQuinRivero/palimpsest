"""Health and capability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_registry
from app.config import Settings, get_settings
from app.models.api import (
    CapabilitiesResponse,
    HealthResponse,
    ParserCapabilitiesResponse,
)
from app.services.ingestion.registry import ParserRegistry

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", version=settings.version)


@router.get("/capabilities", response_model=CapabilitiesResponse, tags=["meta"])
def capabilities(
    settings: Settings = Depends(get_settings),
    registry: ParserRegistry = Depends(get_registry),
) -> CapabilitiesResponse:
    """Describe what this server can parse, and its current limits.

    The client builds its upload accept list from this rather than hardcoding
    formats, which is what makes registering the OCR parser later a
    zero-frontend-change event.
    """
    parsers = []
    for parser in registry.all_parsers():
        caps = parser.capabilities()
        parsers.append(
            ParserCapabilitiesResponse(
                name=parser.name,
                version=parser.version,
                source_format=parser.source_format,
                extensions=sorted(parser.supported_extensions),
                media_types=sorted(parser.supported_media_types),
                preserves_headings=caps.preserves_headings,
                preserves_page_numbers=caps.preserves_page_numbers,
                is_lossy=caps.is_lossy,
                is_async=caps.is_async,
                requires_network=caps.requires_network,
                emits_confidence=caps.emits_confidence,
                emits_bboxes=caps.emits_bboxes,
            )
        )

    return CapabilitiesResponse(
        parsers=parsers,
        max_upload_bytes=settings.max_upload_bytes,
        max_blocks_per_comparison=settings.max_blocks_per_comparison,
        max_tokens_per_comparison=settings.max_tokens_per_comparison,
        default_block_page_limit=settings.default_block_page_limit,
        max_block_page_limit=settings.max_block_page_limit,
        diff_options_defaults=settings.diff_options_defaults,
    )
