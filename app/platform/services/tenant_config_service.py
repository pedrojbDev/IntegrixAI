from dataclasses import dataclass

from ...config import Settings


@dataclass(slots=True)
class TenantConfigService:
    """Env-backed tenant configuration seam for implementation routing."""

    settings: Settings

    def get_implementation_key(self, tenant_id: str) -> str:
        return self.settings.tenant_implementation_map.get(
            tenant_id,
            self.settings.default_tenant_implementation,
        )
