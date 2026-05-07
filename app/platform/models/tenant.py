from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tenant:
    """Future persistent tenant record."""

    tenant_id: str
    implementation_key: str
