from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ...config import Settings
from ...models.call_event import CallEvent
from ...models.vapi_call_cost import VapiCallCost


def prune_operational_data(
    session: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Delete old operational rows according to retention settings."""
    if not settings.db_enabled:
        return {"enabled": False, "call_events_deleted": 0, "vapi_call_costs_deleted": 0}

    reference_time = now or datetime.now(timezone.utc)
    call_events_cutoff = reference_time - timedelta(days=settings.call_events_retention_days)
    vapi_cost_cutoff = reference_time - timedelta(days=settings.vapi_cost_retention_days)

    call_events_result = session.execute(
        delete(CallEvent).where(CallEvent.created_at < call_events_cutoff)
    )
    vapi_cost_result = session.execute(
        delete(VapiCallCost).where(VapiCallCost.synced_at < vapi_cost_cutoff)
    )
    session.commit()

    return {
        "enabled": True,
        "call_events_cutoff": call_events_cutoff.isoformat(),
        "vapi_cost_cutoff": vapi_cost_cutoff.isoformat(),
        "call_events_deleted": call_events_result.rowcount or 0,
        "vapi_call_costs_deleted": vapi_cost_result.rowcount or 0,
    }
