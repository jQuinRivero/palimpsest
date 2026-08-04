"""Application configuration.

``pydantic-settings`` is a separate package under Pydantic v2. Every value here
is overridable by environment variable with the ``PALIMPSEST_`` prefix.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.diff import DiffOptions


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PALIMPSEST_",
        env_file=".env",
        extra="ignore",
    )

    version: str = "0.1.0"

    #: Where the session cache lives. ":memory:" is useful for tests but means
    #: comparisons do not survive a restart, which defeats shareable URLs.
    database_path: str = "palimpsest.db"

    #: Uploads are capped well below anything that would trouble the diff
    #: budget; see docs/11-performance-and-scale.md.
    max_upload_bytes: int = 25 * 1024 * 1024

    max_blocks_per_comparison: int = 12_000
    max_tokens_per_comparison: int = 750_000

    default_block_page_limit: int = 200
    max_block_page_limit: int = 500

    #: Sessions are a cache with a deadline, not a system of record. The
    #: researcher's own files remain the system of record.
    document_ttl_hours: int = 24 * 7
    comparison_ttl_hours: int = 24 * 7

    #: Development runs the frontend on its own port, so CORS is required.
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def diff_options_defaults(self) -> DiffOptions:
        return DiffOptions()


@lru_cache
def get_settings() -> Settings:
    return Settings()
