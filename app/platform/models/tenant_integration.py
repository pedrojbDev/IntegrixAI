from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantIntegration:
    """Placeholder for future tenant integration records."""

    tenant_id: str
    integration_key: str
