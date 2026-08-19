from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models.provider_resource import ProviderResource, ProviderResourceOwnership


ShadowResolutionStatus = Literal[
    "resolved",
    "conflict",
    "insufficient_evidence",
    "missing_provider_org_id",
]


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def normalize_did(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if stripped.lower().startswith("sip:"):
        return None
    digits = "".join(character for character in stripped if character.isdigit())
    if not digits:
        return None
    return f"+{digits}" if stripped.startswith("+") else digits


@dataclass(frozen=True, slots=True)
class VapiInboundIdentityEvidence:
    call_id: str | None
    provider_org_id: str | None
    phone_number_id: str | None
    did: str | None
    telephony_credential_id: str | None
    assistant_id: str | None
    sip_destination: str | None
    sip_header_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchedOwnershipEvidence:
    resource_kind: str
    external_id: str
    tenant_id: str


@dataclass(frozen=True, slots=True)
class ShadowTenantResolution:
    status: ShadowResolutionStatus
    tenant_id: str | None
    source: str | None
    matched: tuple[MatchedOwnershipEvidence, ...]
    conflicting_tenant_ids: tuple[str, ...] = ()


def extract_vapi_inbound_identity(payload: Mapping[str, object]) -> VapiInboundIdentityEvidence:
    """Extract only tenant-relevant evidence without changing productive routing.

    SIP header values are intentionally discarded. A generic ``credentialId`` at the
    call or message level is intentionally ignored because its purpose is ambiguous.
    """

    message = _mapping(payload.get("message"))
    container = message or payload
    call = _mapping(container.get("call")) or container
    phone_number = _mapping(call.get("phoneNumber")) or _mapping(
        container.get("phoneNumber")
    )
    assistant = _mapping(call.get("assistant")) or _mapping(container.get("assistant"))
    destination = _mapping(call.get("destination"))
    transport = _mapping(call.get("transport"))

    raw_to = call.get("to")
    to_mapping = _mapping(raw_to)
    to_text = raw_to if isinstance(raw_to, str) else None
    sip_destination = _text(
        call.get("sipUri"),
        destination.get("sipUri"),
        destination.get("uri"),
        transport.get("sipUri"),
        to_text if to_text and to_text.lower().startswith("sip:") else None,
    )
    did = normalize_did(
        _text(
            to_text,
            to_mapping.get("number"),
            to_mapping.get("phoneNumber"),
            destination.get("number"),
            phone_number.get("number"),
            phone_number.get("phoneNumber"),
        )
    )

    header_names: set[str] = set()
    for candidate in (
        call.get("sipHeaders"),
        container.get("sipHeaders"),
        destination.get("sipHeaders"),
        transport.get("sipHeaders"),
    ):
        if isinstance(candidate, Mapping):
            header_names.update(str(name) for name in candidate if str(name).strip())
        elif isinstance(candidate, list):
            for item in candidate:
                item_mapping = _mapping(item)
                name = _text(item_mapping.get("name"), item_mapping.get("key"))
                if name:
                    header_names.add(name)

    return VapiInboundIdentityEvidence(
        call_id=_text(call.get("id"), call.get("callId"), container.get("callId")),
        provider_org_id=_text(
            call.get("orgId"), container.get("orgId"), phone_number.get("orgId")
        ),
        phone_number_id=_text(
            call.get("phoneNumberId"),
            phone_number.get("id"),
            container.get("phoneNumberId"),
        ),
        did=did,
        telephony_credential_id=_text(
            call.get("telephonyCredentialId"),
            phone_number.get("credentialId"),
            transport.get("telephonyCredentialId"),
        ),
        assistant_id=_text(
            call.get("assistantId"), assistant.get("id"), container.get("assistantId")
        ),
        sip_destination=sip_destination,
        sip_header_names=tuple(sorted(header_names)),
    )


@dataclass(slots=True)
class ProviderIdentityShadowEvaluator:
    """Read-only evaluator for the future persisted resolver.

    It is deliberately not wired into webhooks, tools, syncs, or assistant-request.
    ``assistant`` is evaluated only after authoritative endpoint evidence exists.
    """

    provider: str = "vapi"

    def evaluate(
        self,
        session: Session,
        evidence: VapiInboundIdentityEvidence,
        *,
        occurred_at: datetime | None = None,
    ) -> ShadowTenantResolution:
        if not evidence.provider_org_id:
            return ShadowTenantResolution(
                status="missing_provider_org_id",
                tenant_id=None,
                source=None,
                matched=(),
            )

        at = occurred_at or datetime.now(timezone.utc)
        authoritative_candidates = (
            ("did", evidence.did),
            ("sip_endpoint", evidence.sip_destination),
            ("telephony_credential", evidence.telephony_credential_id),
        )
        phone_matches = self._lookup(
            session,
            provider_org_id=evidence.provider_org_id,
            resource_kind="phone_number",
            external_id=evidence.phone_number_id,
            occurred_at=at,
        )
        fallback_matches = tuple(
            match
            for kind, external_id in authoritative_candidates
            for match in self._lookup(
                session,
                provider_org_id=evidence.provider_org_id,
                resource_kind=kind,
                external_id=external_id,
                occurred_at=at,
            )
        )

        assistant_matches = self._lookup(
            session,
            provider_org_id=evidence.provider_org_id,
            resource_kind="assistant",
            external_id=evidence.assistant_id,
            occurred_at=at,
        )

        # If phoneNumberId is present, it must itself be owned. A weaker identifier
        # may corroborate or conflict, but must not silently replace an unknown phone.
        if evidence.phone_number_id:
            authoritative_matches = (*phone_matches, *fallback_matches)
            source = "phone_number"
        else:
            authoritative_matches = fallback_matches
            source = fallback_matches[0].resource_kind if fallback_matches else None

        all_matches = (*authoritative_matches, *assistant_matches)
        all_tenants = {match.tenant_id for match in all_matches}

        if len(all_tenants) > 1:
            return ShadowTenantResolution(
                status="conflict",
                tenant_id=None,
                source=None,
                matched=all_matches,
                conflicting_tenant_ids=tuple(sorted(all_tenants)),
            )
        if evidence.phone_number_id and not phone_matches:
            return ShadowTenantResolution(
                status="insufficient_evidence",
                tenant_id=None,
                source=None,
                matched=all_matches,
            )
        if not authoritative_matches:
            return ShadowTenantResolution(
                status="insufficient_evidence",
                tenant_id=None,
                source=None,
                matched=all_matches,
            )
        tenant_id = authoritative_matches[0].tenant_id
        return ShadowTenantResolution(
            status="resolved",
            tenant_id=tenant_id,
            source=source,
            matched=all_matches,
        )

    def _lookup(
        self,
        session: Session,
        *,
        provider_org_id: str,
        resource_kind: str,
        external_id: str | None,
        occurred_at: datetime,
    ) -> tuple[MatchedOwnershipEvidence, ...]:
        if not external_id:
            return ()
        normalized_external_id = (
            normalize_did(external_id) if resource_kind == "did" else external_id.strip()
        )
        if not normalized_external_id:
            return ()
        tenant_ids = session.execute(
            select(ProviderResourceOwnership.tenant_id)
            .join(
                ProviderResource,
                ProviderResource.id == ProviderResourceOwnership.provider_resource_id,
            )
            .where(
                ProviderResource.provider == self.provider,
                ProviderResource.provider_org_id == provider_org_id,
                ProviderResource.resource_kind == resource_kind,
                ProviderResource.external_id == normalized_external_id,
                ProviderResourceOwnership.valid_from <= occurred_at,
                or_(
                    ProviderResourceOwnership.valid_to.is_(None),
                    ProviderResourceOwnership.valid_to > occurred_at,
                ),
            )
        ).scalars()
        return tuple(
            MatchedOwnershipEvidence(
                resource_kind=resource_kind,
                external_id=normalized_external_id,
                tenant_id=tenant_id,
            )
            for tenant_id in tenant_ids
        )
