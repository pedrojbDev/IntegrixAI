from ...config import Settings
from .models import TenantResolution


def resolve_tenant_details(
    to_number: str | None,
    settings: Settings,
    *,
    assistant_id: str | None = None,
    phone_number_id: str | None = None,
) -> TenantResolution:
    """Resolve tenant metadata using DID mapping and explicit fallback sources."""
    if to_number and to_number in settings.tenant_map:
        return TenantResolution(
            tenant_id=settings.tenant_map[to_number],
            source="did_map",
            to_number=to_number,
            identifier=to_number,
        )
    if phone_number_id and phone_number_id in settings.tenant_phone_number_map:
        return TenantResolution(
            tenant_id=settings.tenant_phone_number_map[phone_number_id],
            source="phone_number_id_map",
            to_number=to_number,
            identifier=phone_number_id,
        )
    if assistant_id and assistant_id in settings.tenant_assistant_map:
        return TenantResolution(
            tenant_id=settings.tenant_assistant_map[assistant_id],
            source="assistant_map",
            to_number=to_number,
            identifier=assistant_id,
        )
    if to_number:
        return TenantResolution(
            tenant_id=settings.default_tenant,
            source="default_tenant",
            to_number=to_number,
            identifier=to_number,
        )
    return TenantResolution(
        tenant_id=settings.default_tenant,
        source="missing_to_number",
        to_number=None,
        identifier=assistant_id or phone_number_id,
    )


def resolve_tenant(to_number: str | None, settings: Settings) -> str:
    """Resolve tenant id using DID mapping; fall back to default."""
    return resolve_tenant_details(to_number, settings).tenant_id


def should_reject_tenant_resolution(resolution: TenantResolution, settings: Settings) -> bool:
    """Production must not silently route unknown or missing DIDs to the default tenant."""
    return settings.is_production and resolution.used_fallback
