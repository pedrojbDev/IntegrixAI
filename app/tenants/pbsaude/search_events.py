from __future__ import annotations

from contextlib import nullcontext

from sqlalchemy.orm import Session

from ...models.call_event import CallEvent
from ...utils.enums import CallFinalState
from . import slot_guard

TOOL_NAME = "search_providers"
_SAFE_PAYLOAD_KEYS = frozenset(
    {"upstream_code", "recovery_action", "attempt", "provider_count", "reused_result"}
)


def persist_search_event(
    *,
    settings,
    tenant_id: str,
    call_id: str,
    event_type: str,
    session: Session | None = None,
    ok: bool | None = None,
    final_state: CallFinalState | str | None = None,
    error_code: str | None = None,
    payload: dict | None = None,
) -> None:
    """Persist an allowlisted, tenant/call-scoped search lifecycle event."""
    if not settings.db_enabled:
        return
    owns_session = session is None
    try:
        with (slot_guard.SessionLocal() if owns_session else nullcontext(session)) as active_session:
            safe_payload = {
                key: value for key, value in (payload or {}).items()
                if key in _SAFE_PAYLOAD_KEYS and isinstance(value, (str, int, float, bool, type(None)))
            }
            active_session.add(CallEvent(
                tenant_id=tenant_id,
                call_id=call_id,
                tool_name=TOOL_NAME,
                event_type=event_type,
                final_state=(final_state.value if isinstance(final_state, CallFinalState) else final_state),
                ok=ok,
                duration_ms=None,
                error_code=error_code,
                payload_masked=safe_payload,
            ))
            if owns_session:
                active_session.commit()
    except Exception:
        # Operational telemetry must never change the caller-visible outcome.
        return
