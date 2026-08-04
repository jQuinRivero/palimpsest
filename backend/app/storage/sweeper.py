"""Sweeper entry point for expiring session-cache rows."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.storage.store import SessionStore

logger = logging.getLogger(__name__)


def sweep_expired(store: SessionStore, now: datetime | None = None) -> int:
    """Delete expired rows and run SQLite planner maintenance via the store.

    ``VACUUM`` is deliberately not part of the normal sweep: it rewrites the
    database file and belongs in a maintenance window after unusually large
    cache churn or a deliberate reduction in disk budget.
    """

    return store.sweep_expired(now or datetime.now(UTC))


async def run_periodic_sweeper(
    store: SessionStore,
    *,
    interval_seconds: float,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> None:
    """Sweep expired cache rows until cancelled.

    The SQLite work runs in a thread so a slow delete or ``PRAGMA optimize``
    pass never blocks the event loop. One failed pass is logged and the next
    interval still runs.
    """

    while True:
        await sleep(interval_seconds)
        try:
            await asyncio.to_thread(sweep_expired, store)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("session cache sweep failed")
