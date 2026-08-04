"""Sweeper entry point for expiring session-cache rows."""

from __future__ import annotations

from datetime import UTC, datetime

from app.storage.store import SessionStore


def sweep_expired(store: SessionStore, now: datetime | None = None) -> int:
    """Delete expired rows and run SQLite planner maintenance via the store.

    ``VACUUM`` is deliberately not part of the normal sweep: it rewrites the
    database file and belongs in a maintenance window after unusually large
    cache churn or a deliberate reduction in disk budget.
    """

    return store.sweep_expired(now or datetime.now(UTC))
