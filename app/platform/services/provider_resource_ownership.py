from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...models.provider_resource import ProviderResource, ProviderResourceOwnership
from ...models.tenant import TenantRecord
from .provider_identity_shadow import normalize_did


SUPPORTED_RESOURCE_KINDS = frozenset(
    {
        "phone_number",
        "did",
        "sip_endpoint",
        "telephony_credential",
        "assistant",
    }
)


class ProviderResourceOwnershipError(ValueError):
    """Raised when an ownership registration would violate tenant safety."""


@dataclass(frozen=True, slots=True)
class ProviderResourceOwnershipRequest:
    tenant_id: str
    provider: str
    provider_org_id: str
    resource_kind: str
    external_id: str
    valid_from: datetime
    source: str = "operational_validation"
    telephony_credential_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderResourceOwnershipResult:
    action: str
    tenant_id: str
    provider: str
    provider_org_id: str
    resource_kind: str
    external_id: str
    provider_resource_id: str | None
    ownership_id: str | None
    applied: bool


def register_provider_resource_ownership(
    session: Session,
    request: ProviderResourceOwnershipRequest,
    *,
    apply: bool,
) -> ProviderResourceOwnershipResult:
    normalized = _normalize_request(request)
    _lock_identity(session, normalized)
    tenant = session.get(TenantRecord, normalized.tenant_id)
    if tenant is None:
        raise ProviderResourceOwnershipError(
            f"tenant {normalized.tenant_id!r} does not exist"
        )
    if tenant.status != "active":
        raise ProviderResourceOwnershipError(
            f"tenant {normalized.tenant_id!r} is not active"
        )

    resource = session.scalar(
        select(ProviderResource).where(
            ProviderResource.provider == normalized.provider,
            ProviderResource.provider_org_id == normalized.provider_org_id,
            ProviderResource.resource_kind == normalized.resource_kind,
            ProviderResource.external_id == normalized.external_id,
        )
    )
    active_ownership = None
    if resource is not None:
        active_ownership = session.scalar(
            select(ProviderResourceOwnership).where(
                ProviderResourceOwnership.provider_resource_id == resource.id,
                ProviderResourceOwnership.valid_to.is_(None),
            )
        )
        if active_ownership is not None:
            if active_ownership.tenant_id != normalized.tenant_id:
                raise ProviderResourceOwnershipError(
                    "resource already has an active ownership for another tenant"
                )
            _validate_resource_metadata(resource, normalized)
            return _result(
                normalized,
                action="already_owned",
                resource=resource,
                ownership=active_ownership,
                applied=apply,
            )
        overlapping = session.scalar(
            select(func.count(ProviderResourceOwnership.id)).where(
                ProviderResourceOwnership.provider_resource_id == resource.id,
                ProviderResourceOwnership.valid_to > normalized.valid_from,
            )
        )
        if overlapping:
            raise ProviderResourceOwnershipError(
                "requested ownership overlaps historical ownership"
            )

    if not apply:
        return _result(
            normalized,
            action="would_create",
            resource=resource,
            ownership=None,
            applied=False,
        )

    try:
        if resource is None:
            resource = ProviderResource(
                provider=normalized.provider,
                provider_org_id=normalized.provider_org_id,
                resource_kind=normalized.resource_kind,
                external_id=normalized.external_id,
                normalized_value=normalized.external_id,
                telephony_credential_id=normalized.telephony_credential_id,
                configuration_source=normalized.source,
            )
            session.add(resource)
            session.flush()
        else:
            _validate_resource_metadata(resource, normalized)
            if (
                resource.telephony_credential_id is None
                and normalized.telephony_credential_id is not None
            ):
                resource.telephony_credential_id = normalized.telephony_credential_id
        ownership = ProviderResourceOwnership(
            provider_resource_id=resource.id,
            tenant_id=normalized.tenant_id,
            valid_from=normalized.valid_from,
            source=normalized.source,
        )
        session.add(ownership)
        session.flush()
    except IntegrityError as exc:
        raise ProviderResourceOwnershipError(
            "concurrent ownership registration conflict"
        ) from exc
    return _result(
        normalized,
        action="created",
        resource=resource,
        ownership=ownership,
        applied=True,
    )


def _normalize_request(
    request: ProviderResourceOwnershipRequest,
) -> ProviderResourceOwnershipRequest:
    provider = request.provider.strip().lower()
    provider_org_id = request.provider_org_id.strip()
    resource_kind = request.resource_kind.strip().lower()
    tenant_id = request.tenant_id.strip()
    source = request.source.strip()
    if not provider or not provider_org_id or not tenant_id or not source:
        raise ProviderResourceOwnershipError(
            "provider, provider_org_id, tenant_id and source are required"
        )
    if resource_kind not in SUPPORTED_RESOURCE_KINDS:
        raise ProviderResourceOwnershipError(
            f"unsupported resource kind: {resource_kind!r}"
        )
    external_id = request.external_id.strip()
    if resource_kind == "did":
        external_id = normalize_did(external_id) or ""
    if not external_id:
        raise ProviderResourceOwnershipError("external_id is required")
    valid_from = request.valid_from
    if valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=timezone.utc)
    else:
        valid_from = valid_from.astimezone(timezone.utc)
    telephony_credential_id = (
        request.telephony_credential_id.strip()
        if request.telephony_credential_id
        else None
    )
    return ProviderResourceOwnershipRequest(
        tenant_id=tenant_id,
        provider=provider,
        provider_org_id=provider_org_id,
        resource_kind=resource_kind,
        external_id=external_id,
        valid_from=valid_from,
        source=source,
        telephony_credential_id=telephony_credential_id,
    )


def _validate_resource_metadata(
    resource: ProviderResource,
    request: ProviderResourceOwnershipRequest,
) -> None:
    if (
        resource.telephony_credential_id
        and request.telephony_credential_id
        and resource.telephony_credential_id != request.telephony_credential_id
    ):
        raise ProviderResourceOwnershipError(
            "telephony credential conflicts with persisted resource metadata"
        )


def _result(
    request: ProviderResourceOwnershipRequest,
    *,
    action: str,
    resource: ProviderResource | None,
    ownership: ProviderResourceOwnership | None,
    applied: bool,
) -> ProviderResourceOwnershipResult:
    return ProviderResourceOwnershipResult(
        action=action,
        tenant_id=request.tenant_id,
        provider=request.provider,
        provider_org_id=request.provider_org_id,
        resource_kind=request.resource_kind,
        external_id=request.external_id,
        provider_resource_id=resource.id if resource else None,
        ownership_id=ownership.id if ownership else None,
        applied=applied,
    )


def _lock_identity(
    session: Session,
    request: ProviderResourceOwnershipRequest,
) -> None:
    if not session.bind or session.bind.dialect.name != "postgresql":
        return
    material = "|".join(
        (
            request.provider,
            request.provider_org_id,
            request.resource_kind,
            request.external_id,
        )
    )
    digest = sha256(material.encode("utf-8")).digest()
    lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
    session.execute(select(func.pg_advisory_xact_lock(lock_id)))
