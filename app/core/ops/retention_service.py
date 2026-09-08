from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ...config import Settings
from ...models.call_event import CallEvent
from ...models.provider_event_receipt import ProviderEventReceipt
from ...models.vapi_call_cost import VapiCallCost
from ...models.vapi_call_slot_state import VapiCallSlotState
from ...models.vapi_search_execution import VapiSearchExecution
from ...models.vapi_webhook_receipt import VapiWebhookReceipt


def prune_operational_data(
    session: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Delete old operational rows according to retention settings."""
    if not settings.db_enabled:
        return {
            "enabled": False,
            "call_events_deleted": 0,
            "vapi_call_costs_deleted": 0,
            "vapi_call_slot_states_deleted": 0,
            "vapi_search_executions_deleted": 0,
            "vapi_webhook_receipts_deleted": 0,
            "provider_event_receipts_deleted": 0,
        }

    reference_time = now or datetime.now(timezone.utc)
    call_events_cutoff = reference_time - timedelta(days=settings.call_events_retention_days)
    vapi_cost_cutoff = reference_time - timedelta(days=settings.vapi_cost_retention_days)
    provider_receipts_cutoff = call_events_cutoff

    call_events_result = session.execute(
        delete(CallEvent).where(CallEvent.created_at < call_events_cutoff)
    )
    vapi_cost_result = session.execute(
        delete(VapiCallCost).where(VapiCallCost.synced_at < vapi_cost_cutoff)
    )
    slot_state_result = session.execute(
        delete(VapiCallSlotState).where(VapiCallSlotState.expires_at < reference_time)
    )
    search_result = session.execute(
        delete(VapiSearchExecution).where(VapiSearchExecution.expires_at < reference_time)
    )
    receipt_result = session.execute(
        delete(ProviderEventReceipt).where(ProviderEventReceipt.received_at < provider_receipts_cutoff)
    )
    webhook_receipt_result = session.execute(
        delete(VapiWebhookReceipt).where(VapiWebhookReceipt.received_at < provider_receipts_cutoff)
    )
    session.commit()

    return {
        "enabled": True,
        "call_events_cutoff": call_events_cutoff.isoformat(),
        "vapi_cost_cutoff": vapi_cost_cutoff.isoformat(),
        "provider_receipts_cutoff": provider_receipts_cutoff.isoformat(),
        "call_events_deleted": call_events_result.rowcount or 0,
        "vapi_call_costs_deleted": vapi_cost_result.rowcount or 0,
        "vapi_call_slot_states_deleted": slot_state_result.rowcount or 0,
        "vapi_search_executions_deleted": search_result.rowcount or 0,
        "vapi_webhook_receipts_deleted": webhook_receipt_result.rowcount or 0,
        "provider_event_receipts_deleted": receipt_result.rowcount or 0,
    }
