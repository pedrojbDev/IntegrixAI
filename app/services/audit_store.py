from __future__ import annotations

from typing import Any

from ..config import Settings
from ..db import SessionLocal
from ..logging import get_logger
from ..models.call_event import CallEvent

log = get_logger()

SENSITIVE_KEYS = {"cpf", "token", "secret", "authorization", "password"}


def mask_payload(value: Any) -> Any:
    """Mask sensitive fields before persisting payload snapshots."""
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if key_lower in SENSITIVE_KEYS:
                masked[key] = "***"
                continue
            if key_lower == "cpf" and isinstance(item, str):
                digits = "".join(ch for ch in item if ch.isdigit())
                masked[key] = f"***{digits[-4:]}" if digits else "***"
                continue
            masked[key] = mask_payload(item)
        return masked
    if isinstance(value, list):
        return [mask_payload(item) for item in value]
    return value


def record_call_event(
    *,
    settings: Settings,
    tenant_id: str | None,
    call_id: str | None,
    tool_name: str,
    event_type: str,
    final_state: str | None,
    ok: bool | None,
    duration_ms: float | None,
    error_code: str | None,
    payload: dict | None,
) -> None:
    """Persist a call event when DB auditing is enabled."""
    if not settings.db_enabled:
        return

    session = SessionLocal()
    try:
        event = CallEvent(
            tenant_id=tenant_id or "unknown",
            call_id=call_id or "unknown",
            tool_name=tool_name,
            event_type=event_type,
            final_state=final_state,
            ok=ok,
            duration_ms=duration_ms,
            error_code=error_code,
            payload_masked=mask_payload(payload or {}),
        )
        session.add(event)
        session.commit()
    except Exception as exc:
        session.rollback()
        log.warning(
            "audit_store_failed",
            event_type="audit_error",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            reason=str(exc),
        )
    finally:
        session.close()

