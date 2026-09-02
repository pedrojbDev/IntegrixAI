from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

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
_MAX_TRACKED_MESSAGE_HASHES = 32
_MAX_TERMS = 64
_MAX_NGRAM_WORDS = 6
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_KEYPAD_ENTRY_RE = re.compile(
    r"(?:user'?s\s+keypad\s+entry|keypad\s+entry)\s*:\s*([0-9\s.#*-]+)",
    re.IGNORECASE,
)
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
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(_TOKEN_RE.findall(unaccented.lower()))


def keyed_hmac(secret: str, value: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def term_hmacs(secret: str, value: str) -> set[str]:
    tokens = normalize_text(value).split()
    terms: set[str] = set()
    for start in range(len(tokens)):
        for end in range(start + 1, min(len(tokens), start + _MAX_NGRAM_WORDS) + 1):
            terms.add(" ".join(tokens[start:end]))
    return {keyed_hmac(secret, term) for term in sorted(terms)[:_MAX_TERMS]}


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _extract_user_messages(message: Mapping[str, Any]) -> Iterable[str]:
    artifact = _as_mapping(message.get("artifact"))
    candidates = (message.get("messages"), artifact.get("messages"), message.get("conversation"))
    for candidate in candidates:
        collection = _as_mapping(candidate).get("messages") if isinstance(candidate, Mapping) else candidate
        if not isinstance(collection, list):
            continue
        for item in collection:
            item_map = _as_mapping(item)
            if str(item_map.get("role") or "").lower() not in {"user", "customer"}:
                continue
            text = _as_text(item_map.get("message")) or _as_text(item_map.get("content")) or _as_text(item_map.get("text"))
            if text:
                yield text
        return


def _keypad_cpf(value: str) -> str | None:
    match = _KEYPAD_ENTRY_RE.search(value)
    if match is None:
        return None
    digits = "".join(character for character in match.group(1) if character.isdigit())
    return digits if len(digits) == 11 else None


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

    def _capture_slot_provenance(
        self,
        session: Session,
        tenant_id: str,
        call_id: str,
        message: Mapping[str, Any],
        occurred_at: datetime | None,
    ) -> None:
        secret = self.settings.vapi_slot_state_hmac_secret
        if not secret:
            raise VapiEventValidationError("VAPI_SLOT_STATE_HMAC_SECRET is required when slot guard is enabled")
        now = datetime.now(timezone.utc)
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at, now):
            state = VapiCallSlotState(
                tenant_id=tenant_id,
                call_id=call_id,
                phase="cpf",
                city_term_hmacs=[],
                specialty_term_hmacs=[],
                processed_message_hmacs=[],
                expires_at=now + timedelta(hours=self.settings.vapi_slot_state_retention_hours),
            )
            session.add(state)

        processed = set(state.processed_message_hmacs or [])
        for user_text in _extract_user_messages(message):
            message_hash = keyed_hmac(secret, normalize_text(user_text))
            if not normalize_text(user_text) or message_hash in processed:
                continue
            processed.add(message_hash)
            cpf = _keypad_cpf(user_text)
            if state.phase == "cpf" and cpf:
                state.cpf_hmac = keyed_hmac(secret, cpf)
                state.phase = "cidade"
            elif state.phase == "cidade" and not cpf:
                state.city_term_hmacs = sorted(term_hmacs(secret, user_text))
                state.phase = "especialidade"
            elif state.phase == "especialidade" and not cpf:
                state.specialty_term_hmacs = sorted(term_hmacs(secret, user_text))

        state.processed_message_hmacs = sorted(processed)[-_MAX_TRACKED_MESSAGE_HASHES:]
        state.last_event_at = occurred_at or now
        state.expires_at = now + timedelta(hours=self.settings.vapi_slot_state_retention_hours)

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
