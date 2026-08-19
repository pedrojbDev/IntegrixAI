from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models.provider_event_receipt import ProviderEventReceipt
from ...models.voice_call import VoiceCall
from .provider_identity_shadow import (
    ProviderIdentityShadowEvaluator,
    ShadowTenantResolution,
    VapiInboundIdentityEvidence,
)


@dataclass(frozen=True, slots=True)
class InboundCallObservation:
    provider: str
    source: str
    event_type: str
    evidence: VapiInboundIdentityEvidence
    raw_payload: dict[str, Any]
    external_event_id: str | None = None
    occurred_at: datetime | None = None
    provider_created_at: datetime | None = None
    provider_updated_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    provider_status: str | None = None


@dataclass(frozen=True, slots=True)
class VoiceCallReconciliationResult:
    voice_call: VoiceCall | None
    receipt: ProviderEventReceipt
    duplicate: bool
    identity_result: str


class VoiceCallReconciliationService:
    """Converge inbound observations without ever reassigning a fixed tenant."""

    def reconcile(
        self,
        session: Session,
        observation: InboundCallObservation,
        *,
        received_at: datetime | None = None,
    ) -> VoiceCallReconciliationResult:
        received_at = _as_utc(received_at or datetime.now(timezone.utc))
        payload_sanitized = self._sanitize(observation)
        payload_sha256 = self._payload_hash(observation.raw_payload or payload_sanitized)
        receipt_key = self._receipt_key(observation, payload_sha256)
        self._lock_call_identity(
            session,
            observation.provider,
            observation.evidence.call_id or receipt_key,
        )
        existing_receipt = session.execute(
            select(ProviderEventReceipt).where(
                ProviderEventReceipt.provider == observation.provider,
                ProviderEventReceipt.receipt_key == receipt_key,
            )
        ).scalar_one_or_none()
        if existing_receipt is not None:
            voice_call = (
                session.get(VoiceCall, existing_receipt.voice_call_id)
                if existing_receipt.voice_call_id
                else None
            )
            return VoiceCallReconciliationResult(
                voice_call=voice_call,
                receipt=existing_receipt,
                duplicate=True,
                identity_result=existing_receipt.identity_result,
            )

        call_id = observation.evidence.call_id
        if not call_id:
            receipt = self._new_receipt(
                observation,
                receipt_key=receipt_key,
                payload_sha256=payload_sha256,
                payload_sanitized=payload_sanitized,
                received_at=received_at,
                voice_call=None,
                processing_status="quarantined",
                identity_result="missing_call_id",
            )
            session.add(receipt)
            session.flush()
            return VoiceCallReconciliationResult(
                voice_call=None,
                receipt=receipt,
                duplicate=False,
                identity_result="missing_call_id",
            )

        voice_call = session.execute(
            select(VoiceCall)
            .where(
                VoiceCall.provider == observation.provider,
                VoiceCall.provider_call_id == call_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        is_new = voice_call is None
        if voice_call is None:
            identity_observed_at = self._identity_time(observation, received_at)
            voice_call = VoiceCall(
                provider=observation.provider,
                provider_org_id=observation.evidence.provider_org_id,
                provider_call_id=call_id,
                direction="inbound",
                identity_status="quarantined",
                reconciliation_status="pending",
                identity_observed_at=identity_observed_at,
                phone_number_id=observation.evidence.phone_number_id,
                did=observation.evidence.did,
                telephony_credential_id=observation.evidence.telephony_credential_id,
                assistant_id=observation.evidence.assistant_id,
                sip_destination=observation.evidence.sip_destination,
                last_observed_at=received_at,
            )
            session.add(voice_call)
            session.flush()

        incoming_identity_time = self._identity_time(observation, received_at)
        identity_time = _as_utc(
            voice_call.identity_observed_at or incoming_identity_time
        )
        if voice_call.tenant_id is None and incoming_identity_time < identity_time:
            identity_time = incoming_identity_time
            voice_call.identity_observed_at = incoming_identity_time
        candidate_evidence, field_conflict = self._merge_evidence(
            voice_call, observation.evidence
        )
        evaluator = ProviderIdentityShadowEvaluator(provider=observation.provider)
        identity = evaluator.evaluate(
            session,
            candidate_evidence,
            occurred_at=identity_time,
        )
        processing_status, identity_result = self._apply_identity(
            voice_call,
            identity,
            candidate_evidence,
            field_conflict=field_conflict,
            received_at=received_at,
            is_new=is_new,
        )
        self._apply_lifecycle(voice_call, observation, received_at)

        receipt = self._new_receipt(
            observation,
            receipt_key=receipt_key,
            payload_sha256=payload_sha256,
            payload_sanitized=payload_sanitized,
            received_at=received_at,
            voice_call=voice_call,
            processing_status=processing_status,
            identity_result=identity_result,
        )
        session.add(receipt)
        session.flush()
        return VoiceCallReconciliationResult(
            voice_call=voice_call,
            receipt=receipt,
            duplicate=False,
            identity_result=identity_result,
        )

    @staticmethod
    def _identity_time(
        observation: InboundCallObservation, received_at: datetime
    ) -> datetime:
        return _as_utc(
            observation.started_at
            or observation.provider_created_at
            or observation.occurred_at
            or received_at
        )

    @staticmethod
    def _merge_evidence(
        voice_call: VoiceCall,
        incoming: VapiInboundIdentityEvidence,
    ) -> tuple[VapiInboundIdentityEvidence, tuple[str, ...]]:
        conflicts: list[str] = []
        stable_fields = (
            ("provider_org_id", voice_call.provider_org_id, incoming.provider_org_id),
            ("phone_number_id", voice_call.phone_number_id, incoming.phone_number_id),
            ("did", voice_call.did, incoming.did),
            (
                "telephony_credential_id",
                voice_call.telephony_credential_id,
                incoming.telephony_credential_id,
            ),
            ("sip_destination", voice_call.sip_destination, incoming.sip_destination),
        )
        for name, current, new in stable_fields:
            if current and new and current != new:
                conflicts.append(name)
        return (
            replace(
                incoming,
                provider_org_id=incoming.provider_org_id or voice_call.provider_org_id,
                phone_number_id=incoming.phone_number_id or voice_call.phone_number_id,
                did=incoming.did or voice_call.did,
                telephony_credential_id=(
                    incoming.telephony_credential_id
                    or voice_call.telephony_credential_id
                ),
                assistant_id=incoming.assistant_id or voice_call.assistant_id,
                sip_destination=incoming.sip_destination or voice_call.sip_destination,
            ),
            tuple(conflicts),
        )

    @staticmethod
    def _apply_identity(
        voice_call: VoiceCall,
        identity: ShadowTenantResolution,
        evidence: VapiInboundIdentityEvidence,
        *,
        field_conflict: tuple[str, ...],
        received_at: datetime,
        is_new: bool,
    ) -> tuple[str, str]:
        resolved_tenant = identity.tenant_id if identity.status == "resolved" else None
        conflicts_with_fixed_tenant = bool(
            voice_call.tenant_id
            and resolved_tenant
            and voice_call.tenant_id != resolved_tenant
        )
        is_conflict = bool(field_conflict) or identity.status == "conflict" or (
            conflicts_with_fixed_tenant
        )
        if is_conflict:
            if voice_call.tenant_id is None:
                voice_call.identity_status = "quarantined"
            voice_call.reconciliation_status = "conflict"
            return "conflict", "conflict"

        if voice_call.tenant_id is not None:
            # Canonical tenant wins over sparse observations and later mapping changes.
            if voice_call.reconciliation_status != "conflict":
                voice_call.reconciliation_status = "consistent"
            VoiceCallReconciliationService._fill_identity_fields(voice_call, evidence)
            return "accepted", "canonical_tenant"

        if identity.status == "resolved" and resolved_tenant:
            voice_call.tenant_id = resolved_tenant
            voice_call.tenant_fixed_at = received_at
            voice_call.identity_status = "admitted"
            voice_call.identity_source = identity.source
            voice_call.reconciliation_status = "consistent"
            VoiceCallReconciliationService._fill_identity_fields(voice_call, evidence)
            return "accepted", "resolved"

        voice_call.identity_status = "quarantined"
        if voice_call.reconciliation_status != "conflict":
            voice_call.reconciliation_status = identity.status
        if is_new or identity.status != "conflict":
            VoiceCallReconciliationService._fill_identity_fields(voice_call, evidence)
        return "quarantined", identity.status

    @staticmethod
    def _fill_identity_fields(
        voice_call: VoiceCall, evidence: VapiInboundIdentityEvidence
    ) -> None:
        for name in (
            "provider_org_id",
            "phone_number_id",
            "did",
            "telephony_credential_id",
            "sip_destination",
        ):
            current = getattr(voice_call, name)
            incoming = getattr(evidence, name)
            if current is None and incoming is not None:
                setattr(voice_call, name, incoming)
        if evidence.assistant_id:
            voice_call.assistant_id = evidence.assistant_id

    @staticmethod
    def _apply_lifecycle(
        voice_call: VoiceCall,
        observation: InboundCallObservation,
        received_at: datetime,
    ) -> None:
        incoming_updated = (
            _as_utc(observation.provider_updated_at)
            if observation.provider_updated_at
            else None
        )
        current_updated = (
            _as_utc(voice_call.provider_updated_at)
            if voice_call.provider_updated_at
            else None
        )
        apply_snapshot = (
            incoming_updated is not None
            and (current_updated is None or incoming_updated >= current_updated)
        ) or (incoming_updated is None and voice_call.provider_status is None)
        if apply_snapshot:
            voice_call.provider_status = observation.provider_status
            voice_call.provider_created_at = (
                observation.provider_created_at or voice_call.provider_created_at
            )
            voice_call.provider_updated_at = (
                observation.provider_updated_at or voice_call.provider_updated_at
            )
            voice_call.started_at = observation.started_at or voice_call.started_at
            voice_call.ended_at = observation.ended_at or voice_call.ended_at
            if observation.duration_seconds is not None:
                voice_call.duration_seconds = observation.duration_seconds
        else:
            voice_call.provider_created_at = (
                voice_call.provider_created_at or observation.provider_created_at
            )
            voice_call.started_at = voice_call.started_at or observation.started_at
        if received_at > _as_utc(voice_call.last_observed_at):
            voice_call.last_observed_at = received_at

    @staticmethod
    def _new_receipt(
        observation: InboundCallObservation,
        *,
        receipt_key: str,
        payload_sha256: str,
        payload_sanitized: dict[str, Any],
        received_at: datetime,
        voice_call: VoiceCall | None,
        processing_status: str,
        identity_result: str,
    ) -> ProviderEventReceipt:
        return ProviderEventReceipt(
            provider=observation.provider,
            receipt_key=receipt_key,
            source=observation.source,
            event_type=observation.event_type,
            external_event_id=observation.external_event_id,
            provider_org_id=observation.evidence.provider_org_id,
            provider_call_id=observation.evidence.call_id,
            voice_call_id=voice_call.id if voice_call else None,
            processing_status=processing_status,
            identity_result=identity_result,
            payload_sha256=payload_sha256,
            payload_sanitized=payload_sanitized,
            provider_occurred_at=(
                observation.provider_updated_at or observation.occurred_at
            ),
            received_at=received_at,
        )

    @staticmethod
    def _sanitize(observation: InboundCallObservation) -> dict[str, Any]:
        evidence = observation.evidence
        return {
            "call_id": evidence.call_id,
            "provider_org_id": evidence.provider_org_id,
            "phone_number_id": evidence.phone_number_id,
            "did": evidence.did,
            "telephony_credential_id": evidence.telephony_credential_id,
            "assistant_id": evidence.assistant_id,
            "sip_destination": evidence.sip_destination,
            "sip_header_names": list(evidence.sip_header_names),
            "provider_status": observation.provider_status,
            "provider_created_at": _iso(observation.provider_created_at),
            "provider_updated_at": _iso(observation.provider_updated_at),
            "started_at": _iso(observation.started_at),
            "ended_at": _iso(observation.ended_at),
            "duration_seconds": observation.duration_seconds,
        }

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _receipt_key(
        observation: InboundCallObservation, payload_sha256: str
    ) -> str:
        identity = observation.external_event_id or payload_sha256
        material = "|".join(
            (
                observation.source,
                observation.event_type,
                observation.evidence.provider_org_id or "",
                identity,
            )
        )
        return sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _lock_call_identity(
        session: Session,
        provider: str,
        call_identity: str,
    ) -> None:
        if not session.bind or session.bind.dialect.name != "postgresql":
            return
        digest = sha256(f"{provider}|{call_identity}".encode("utf-8")).digest()
        lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
        session.execute(select(func.pg_advisory_xact_lock(lock_id)))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value else None
