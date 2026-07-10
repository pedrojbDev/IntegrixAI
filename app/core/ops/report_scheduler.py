from __future__ import annotations

import asyncio

from ...config import Settings
from ...logging import get_logger
from .report_delivery_service import run_daily_operational_report_if_due

CHECK_INTERVAL_SECONDS = 60

log = get_logger()
_scheduler_task: asyncio.Task[None] | None = None


def start_daily_report_scheduler(settings: Settings) -> None:
    """Start the in-process scheduler only when the delivery is explicitly enabled."""
    global _scheduler_task

    if not settings.daily_report_enabled:
        return
    if _scheduler_task is not None and not _scheduler_task.done():
        return

    _scheduler_task = asyncio.create_task(_run_scheduler(settings))


def stop_daily_report_scheduler() -> None:
    global _scheduler_task

    if _scheduler_task is not None:
        _scheduler_task.cancel()
    _scheduler_task = None


async def _run_scheduler(settings: Settings) -> None:
    log.info(
        "daily_operational_report_scheduler_started",
        event_type="ops_report_scheduler",
        scheduled_hour_brasilia=settings.daily_report_hour_brasilia,
    )
    while True:
        try:
            await asyncio.to_thread(run_daily_operational_report_if_due, settings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(
                "daily_operational_report_scheduler_failed",
                event_type="ops_report_scheduler",
                reason=str(exc),
            )
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
