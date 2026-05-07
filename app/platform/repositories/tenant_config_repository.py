from typing import Protocol


class TenantConfigRepository(Protocol):
    """Protocol for future tenant-scoped config persistence."""

    def get_implementation_key(self, tenant_id: str) -> str | None:
        ...
