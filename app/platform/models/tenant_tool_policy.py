from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantToolPolicy:
    """Placeholder for future tool policy persistence."""

    tenant_id: str
    tool_name: str
    enabled: bool
