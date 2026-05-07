from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeatureFlagService:
    """Placeholder seam for future platform feature flags."""

    default_enabled: bool = True
