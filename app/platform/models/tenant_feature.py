from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantFeature:
    """Placeholder for future tenant feature flags."""

    tenant_id: str
    feature_key: str
    enabled: bool
