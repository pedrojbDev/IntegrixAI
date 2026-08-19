from dataclasses import dataclass
from typing import Literal


TenantResolutionSource = Literal[
    "did_map",
    "assistant_map",
    "phone_number_id_map",
    "default_tenant",
    "missing_to_number",
]


@dataclass(frozen=True, slots=True)
class TenantResolution:
    tenant_id: str
    source: TenantResolutionSource
    to_number: str | None
    identifier: str | None = None

    @property
    def used_fallback(self) -> bool:
        return self.source in {"default_tenant", "missing_to_number"}
