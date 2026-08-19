from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...config import Settings
from ...db import SessionLocal
from ...logging import get_logger
from ...models.tool_invocation import ToolBusinessErrorAttempt, ToolInvocationResult
from ...utils.enums import CallFinalState

log = get_logger()


def get_cached_tool_result(
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
    tool_call_id: str | None,
) -> dict | None:
    if not settings.db_enabled or not tool_call_id:
        return None

    session = SessionLocal()
    try:
        row = session.execute(
            select(ToolInvocationResult).where(
                ToolInvocationResult.tenant_id == tenant_id,
                ToolInvocationResult.call_id == call_id,
                ToolInvocationResult.tool_call_id == tool_call_id,
            )
        ).scalar_one_or_none()
        return dict(row.result_payload) if row is not None else None
    except Exception as exc:
        log.warning(
            "tool_idempotency_lookup_failed",
            event_type="idempotency_error",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_call_id=tool_call_id,
            reason=str(exc),
        )
        return None
    finally:
        session.close()


def save_tool_result(
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
    tool_call_id: str | None,
    tool_name: str,
    ok: bool,
    final_state: CallFinalState,
    error_code: str | None,
    duration_ms: float | None,
    result_payload: dict,
) -> None:
    if not settings.db_enabled or not tool_call_id:
        return

    session = SessionLocal()
    try:
        row = ToolInvocationResult(
            tenant_id=tenant_id,
            call_id=call_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            ok=ok,
            final_state=final_state.value,
            error_code=error_code,
            duration_ms=duration_ms,
            result_payload=result_payload,
        )
        session.add(row)
        session.commit()
    except IntegrityError:
        session.rollback()
    except Exception as exc:
        session.rollback()
        log.warning(
            "tool_idempotency_save_failed",
            event_type="idempotency_error",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            reason=str(exc),
        )
    finally:
        session.close()


def record_business_error_attempt(
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
    tool_name: str,
    field: str | None,
    upstream_code: str,
) -> int:
    if not settings.db_enabled:
        return 1

    normalized_field = field or "unknown"
    session = SessionLocal()
    try:
        row = session.execute(
            select(ToolBusinessErrorAttempt).where(
                ToolBusinessErrorAttempt.tenant_id == tenant_id,
                ToolBusinessErrorAttempt.call_id == call_id,
                ToolBusinessErrorAttempt.tool_name == tool_name,
                ToolBusinessErrorAttempt.field == normalized_field,
                ToolBusinessErrorAttempt.upstream_code == upstream_code,
            )
        ).scalar_one_or_none()
        if row is None:
            row = ToolBusinessErrorAttempt(
                tenant_id=tenant_id,
                call_id=call_id,
                tool_name=tool_name,
                field=normalized_field,
                upstream_code=upstream_code,
                attempts=1,
            )
            session.add(row)
            attempt = 1
        else:
            row.attempts += 1
            attempt = row.attempts
        session.commit()
        return attempt
    except IntegrityError:
        session.rollback()
        return record_business_error_attempt(
            settings=settings,
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            field=normalized_field,
            upstream_code=upstream_code,
        )
    except Exception as exc:
        session.rollback()
        log.warning(
            "tool_business_error_attempt_failed",
            event_type="business_error_attempt",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            field=normalized_field,
            upstream_code=upstream_code,
            reason=str(exc),
        )
        return 1
    finally:
        session.close()
