from typing import Protocol

from ..models.tenant import Tenant


class TenantRepository(Protocol):
    """Protocol for future tenant persistence."""

    def get(self, tenant_id: str) -> Tenant | None:
        ...
