from __future__ import annotations

import asyncio

from ...config import Settings
from ...db import SessionLocal
from ...logging import get_logger
from .cost_sync_service import VapiCostSyncService

log = get_logger()
_scheduler_task: asyncio.Task[None] | None = None


def start_cost_sync_scheduler(settings: Settings) -> None:
    global _scheduler_task
    if (
        not settings.ops_cost_sync_enabled
        or not settings.db_enabled
        or not settings.vapi_api_key
    ):
        return
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_run_scheduler(settings))


def stop_cost_sync_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
    _scheduler_task = None


async def _run_scheduler(settings: Settings) -> None:
    log.info(
        "ops_cost_sync_scheduler_started",
        event_type="ops_cost_sync_scheduler",
        interval_seconds=settings.ops_cost_sync_interval_seconds,
    )
    while True:
        try:
            await asyncio.to_thread(_run_once, settings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(
                "ops_cost_sync_scheduler_failed",
                event_type="ops_cost_sync_scheduler",
                reason=str(exc),
            )
        await asyncio.sleep(settings.ops_cost_sync_interval_seconds)


def _run_once(settings: Settings) -> None:
    session = SessionLocal()
    try:
        VapiCostSyncService(settings).sync(session)
    finally:
        session.close()
