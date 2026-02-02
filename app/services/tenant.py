from ..config import Settings


def resolve_tenant(to_number: str | None, settings: Settings) -> str:
    """Resolve tenant id using DID mapping; fall back to default."""
    if to_number and to_number in settings.tenant_map:
        return settings.tenant_map[to_number]
    return settings.default_tenant
