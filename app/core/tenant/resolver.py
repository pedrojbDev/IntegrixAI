from ...config import Settings
from .models import TenantResolution


def resolve_tenant_details(to_number: str | None, settings: Settings) -> TenantResolution:
    """Resolve tenant metadata using DID mapping and explicit fallback sources."""
    if to_number and to_number in settings.tenant_map:
        return TenantResolution(
            tenant_id=settings.tenant_map[to_number],
            source="did_map",
            to_number=to_number,
        )
    if to_number:
        return TenantResolution(
            tenant_id=settings.default_tenant,
            source="default_tenant",
            to_number=to_number,
        )
    return TenantResolution(
        tenant_id=settings.default_tenant,
        source="missing_to_number",
        to_number=None,
    )


def resolve_tenant(to_number: str | None, settings: Settings) -> str:
    """Resolve tenant id using DID mapping; fall back to default."""
    return resolve_tenant_details(to_number, settings).tenant_id


def should_reject_tenant_resolution(resolution: TenantResolution, settings: Settings) -> bool:
    """Production must not silently route unknown or missing DIDs to the default tenant."""
    return settings.is_production and resolution.used_fallback
