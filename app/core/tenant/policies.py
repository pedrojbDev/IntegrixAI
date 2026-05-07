from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantPolicy:
    """Placeholder for future tenant-scoped policies."""

    tenant_id: str
