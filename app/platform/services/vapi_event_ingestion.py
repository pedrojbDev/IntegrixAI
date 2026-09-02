from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import Settings
from ...logging import get_logger
from ...models.call_event import CallEvent
from ...models.vapi_call_slot_state import VapiCallSlotState
from ...models.vapi_webhook_receipt import VapiWebhookReceipt
from ...utils.enums import CallFinalState
from ...core.tenant.resolver import resolve_tenant_details, should_reject_tenant_resolution
from .provider_identity_shadow import extract_vapi_inbound_identity


SUPPORTED_EVENT_TYPES = frozenset({"conversation-update", "status-update", "end-of-call-report"})
TRANSFER_SUCCESS_REASONS = frozenset({"assistant-forwarded-call", "assistant-forwarded"})
TRANSFER_FAILURE_MARKER = "error-transfer-failed"
AGENT_NORMAL_END_REASONS = frozenset(
    {
        "assistant-ended-call",
        "assistant-ended-call-after-message-spoken",
        "assistant-ended-call-with-hangup-task",
        "assistant-said-end-call-phrase",
    }
)
CUSTOMER_NORMAL_END_REASONS = frozenset({"customer-ended-call"})
NORMAL_END_REASONS = AGENT_NORMAL_END_REASONS | CUSTOMER_NORMAL_END_REASONS
log = get_logger()


class VapiEventValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VapiIngestResult:
    accepted: bool
    duplicate: bool
    tenant_id: str | None
    event_type: str


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_datetime(value: object) -> datetime | None:
    stamp = event_time(value)
    if stamp is None or not 0 <= stamp <= 253402300799000:
        return None
    return datetime.fromtimestamp(stamp / 1000, timezone.utc)


# Compatibility exports; tenant reducers share these provider-neutral primitives.
from .vapi_conversation import capture_conversation, event_time, keyed_hmac, lock_call, normalize_text, term_hmacs


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class VapiEventIngestionService:
    """Safely ingests Vapi lifecycle events without retaining conversation content."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def ingest(self, session: Session, payload: Mapping[str, Any]) -> VapiIngestResult:
        message = _as_mapping(payload.get("message"))
        event_type = _as_text(message.get("type"))
        call = _as_mapping(message.get("call"))
        call_id = _as_text(call.get("id") or call.get("callId"))
        if not event_type or not call_id:
            raise VapiEventValidationError("Vapi event requires message.type and message.call.id")

        evidence = extract_vapi_inbound_identity(payload)
        resolution = resolve_tenant_details(
            evidence.did,
            self.settings,
            assistant_id=evidence.assistant_id,
            phone_number_id=evidence.phone_number_id,
        )
        if should_reject_tenant_resolution(resolution, self.settings):
            log.warning(
                "vapi_event_tenant_rejected",
                event_type="vapi_event",
                call_id=call_id,
                resolution_source=resolution.source,
            )
            raise VapiEventValidationError("tenant could not be resolved")
        tenant_id = resolution.tenant_id
        lock_call(session, tenant_id, call_id)
        payload_hash = _payload_sha256(payload)
        receipt_key = hashlib.sha256(f"{tenant_id}:{payload_hash}".encode("utf-8")).hexdigest()
        existing = session.scalar(
            select(VapiWebhookReceipt.id).where(
                VapiWebhookReceipt.receipt_key == receipt_key,
            )
        )
        if existing:
            return VapiIngestResult(True, True, tenant_id, event_type)

        ended_reason = _as_text(message.get("endedReason") or call.get("endedReason"))
        status = _as_text(message.get("status") or call.get("status"))
        occurred_at = _parse_datetime(message.get("timestamp") or message.get("endedAt"))
        receipt = VapiWebhookReceipt(
            tenant_id=tenant_id,
            receipt_key=receipt_key,
            source="webhook",
            event_type=event_type,
            external_event_id=_as_text(message.get("id") or message.get("eventId")),
            provider_org_id=evidence.provider_org_id,
            provider_call_id=call_id,
            processing_status="processing",
            identity_result=resolution.source,
            payload_sha256=payload_hash,
            payload_sanitized={
                "event_type": event_type,
                "call_id": call_id,
                "status": status,
                "ended_reason": ended_reason,
                "tenant_id": tenant_id,
            },
            provider_occurred_at=occurred_at,
        )
        session.add(receipt)

        if event_type == "conversation-update" and self.settings.vapi_slot_guard_enabled:
            self._capture_slot_provenance(session, tenant_id, call_id, message, occurred_at)
        elif event_type == "status-update" and status == "forwarding":
            self._add_call_event(
                session,
                tenant_id=tenant_id,
                call_id=call_id,
                event_type="vapi_native_transfer_started",
                ok=None,
                final_state=None,
                error_code=None,
                payload={"source": "status-update", "status": "forwarding"},
            )
        elif event_type == "end-of-call-report":
            self._record_end_outcome(session, tenant_id, call_id, ended_reason)

        if event_type == "end-of-call-report" or (event_type == "status-update" and status == "forwarding"):
            state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
            if state is None:
                state = VapiCallSlotState(tenant_id=tenant_id, call_id=call_id,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=self.settings.vapi_slot_state_retention_hours))
                session.add(state)
            meta = dict(state.conversation_meta or {})
            # An end report is final even if older lifecycle events arrive later.
            stamp = event_time(message.get("timestamp")) or 0
            if event_type == "end-of-call-report" or (
                meta.get("terminal") != "ended" and stamp >= meta.get("terminal_at", 0)
            ):
                meta.update(terminal="ended" if event_type == "end-of-call-report" else "forwarding",
                            terminal_at=stamp)
            state.conversation_meta = meta
        elif event_type == "status-update" and status == "in-progress":
            state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
            meta = dict(state.conversation_meta or {}) if state else {}
            stamp = event_time(message.get("timestamp")) or 0
            if state and meta.get("terminal") != "ended" and stamp > meta.get("terminal_at", 0):
                # A provider-confirmed return to active conversation can follow
                # a failed transfer. Never reopen a call with an end report.
                meta.pop("terminal", None)
                meta["terminal_at"] = stamp
                state.conversation_meta = meta
        receipt.processing_status = "succeeded" if event_type in SUPPORTED_EVENT_TYPES else "ignored"
        session.commit()
        return VapiIngestResult(True, False, tenant_id, event_type)

    def record_cost_sync_handoff(
        self,
        session: Session,
        *,
        tenant_id: str | None,
        call_id: str,
        ended_reason: str | None,
    ) -> bool:
        if not tenant_id or not ended_reason:
            return False
        if ended_reason not in TRANSFER_SUCCESS_REASONS:
            return False
        return self._record_handoff_success(session, tenant_id, call_id, source="cost_sync")

    def record_cost_sync_terminal_outcome(
        self,
        session: Session,
        *,
        tenant_id: str | None,
        call_id: str,
        ended_reason: str | None,
    ) -> str | None:
        """Rebuild a terminal outcome from a sanitized Vapi cost snapshot.

        The semantic receipts used by the underlying recorders make this safe
        to replay for an individual tenant or across the full retained range.
        """
        if not tenant_id or not ended_reason:
            return None
        if ended_reason in TRANSFER_SUCCESS_REASONS:
            return (
                "successful_handoff"
                if self._record_handoff_success(session, tenant_id, call_id, source="cost_sync")
                else None
            )
        if ended_reason in NORMAL_END_REASONS:
            return (
                "normal_completion"
                if self._record_normal_completion(
                    session, tenant_id, call_id, ended_reason=ended_reason
                )
                else None
            )
        return None

    def _capture_slot_provenance(self, session, tenant_id, call_id, message, occurred_at) -> None:
        capture_conversation(session, self.settings, tenant_id, call_id, message)

    def _record_end_outcome(
        self,
        session: Session,
        tenant_id: str,
        call_id: str,
        ended_reason: str | None,
    ) -> None:
        if ended_reason in TRANSFER_SUCCESS_REASONS:
            self._record_handoff_success(session, tenant_id, call_id, source="end-of-call-report")
        elif ended_reason and TRANSFER_FAILURE_MARKER in ended_reason:
            self._add_call_event(
                session,
                tenant_id=tenant_id,
                call_id=call_id,
                event_type="vapi_native_transfer_failed",
                ok=False,
                final_state=None,
                error_code="TRANSFER_FAILED",
                payload={"source": "end-of-call-report", "ended_reason": ended_reason},
            )
        elif ended_reason in NORMAL_END_REASONS:
            self._record_normal_completion(session, tenant_id, call_id, ended_reason=ended_reason)

    def _record_normal_completion(
        self,
        session: Session,
        tenant_id: str,
        call_id: str,
        *,
        ended_reason: str,
    ) -> bool:
        """Record an idempotent normal terminal outcome without storing call content."""
        semantic_key = hashlib.sha256(
            f"normal-call-completion:{tenant_id}:{call_id}".encode("utf-8")
        ).hexdigest()
        existing = session.scalar(
            select(VapiWebhookReceipt.id).where(
                VapiWebhookReceipt.receipt_key == semantic_key,
            )
        )
        if existing:
            return False
        final_state = (
            CallFinalState.ENCERRADA_USUARIO.value
            if ended_reason in CUSTOMER_NORMAL_END_REASONS
            else CallFinalState.ENCERRADA_AGENTE.value
        )
        session.add(
            VapiWebhookReceipt(
                tenant_id=tenant_id,
                receipt_key=semantic_key,
                source="end-of-call-report",
                event_type="normal_call_completion",
                provider_call_id=call_id,
                processing_status="succeeded",
                identity_result="tenant_scoped",
                payload_sha256=semantic_key,
                payload_sanitized={
                    "event_type": "normal_call_completion",
                    "call_id": call_id,
                    "ended_reason": ended_reason,
                    "tenant_id": tenant_id,
                },
            )
        )
        self._add_call_event(
            session,
            tenant_id=tenant_id,
            call_id=call_id,
            event_type="vapi_normal_call_completed",
            ok=True,
            final_state=final_state,
            error_code=None,
            payload={"source": "end-of-call-report", "ended_reason": ended_reason},
        )
        return True

    def _record_handoff_success(self, session: Session, tenant_id: str, call_id: str, *, source: str) -> bool:
        semantic_key = hashlib.sha256(
            f"native-transfer-success:{tenant_id}:{call_id}".encode("utf-8")
        ).hexdigest()
        existing = session.scalar(
            select(VapiWebhookReceipt.id).where(
                VapiWebhookReceipt.receipt_key == semantic_key,
            )
        )
        if existing:
            return False
        session.add(
            VapiWebhookReceipt(
                tenant_id=tenant_id,
                receipt_key=semantic_key,
                source=source,
                event_type="native_transfer_success",
                provider_call_id=call_id,
                processing_status="succeeded",
                identity_result="tenant_scoped",
                payload_sha256=semantic_key,
                payload_sanitized={"event_type": "native_transfer_success", "call_id": call_id, "source": source, "tenant_id": tenant_id},
            )
        )
        self._add_call_event(
            session,
            tenant_id=tenant_id,
            call_id=call_id,
            event_type="vapi_native_transfer_completed",
            ok=True,
            final_state=CallFinalState.TRANSFERIDA_HUMANO.value,
            error_code=None,
            payload={"source": source},
        )
        return True

    @staticmethod
    def _add_call_event(
        session: Session,
        *,
        tenant_id: str,
        call_id: str,
        event_type: str,
        ok: bool | None,
        final_state: str | None,
        error_code: str | None,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            CallEvent(
                tenant_id=tenant_id,
                call_id=call_id,
                tool_name=(
                    "vapi_native_transfer"
                    if event_type.startswith("vapi_native_transfer")
                    else "vapi_call_lifecycle"
                ),
                event_type=event_type,
                final_state=final_state,
                ok=ok,
                duration_ms=None,
                error_code=error_code,
                payload_masked=payload,
            )
        )


def _is_expired(value: datetime, now: datetime) -> bool:
    expires_at = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return expires_at <= now
