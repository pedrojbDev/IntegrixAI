from dataclasses import dataclass
from typing import Literal


TenantResolutionSource = Literal["did_map", "default_tenant", "missing_to_number"]


@dataclass(frozen=True, slots=True)
class TenantResolution:
    tenant_id: str
    source: TenantResolutionSource
    to_number: str | None

    @property
    def used_fallback(self) -> bool:
        return self.source != "did_map"
