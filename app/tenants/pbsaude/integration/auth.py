from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ....config import Settings
from .client import ServiceUnavailable


@dataclass(slots=True)
class ExternalApiTenantConfig:
    base_url: str
    provider_search_path: str
    auth_type: str
    token: str | None
    username: str | None
    password: str | None
    timeout_seconds: float


def resolve_external_api_tenant_config(
    settings: Settings,
    tenant_id: str,
) -> ExternalApiTenantConfig:
    tenant_raw = settings.external_api_tenant_configs.get(tenant_id) or {}

    base_url = _as_optional_string(tenant_raw.get("base_url")) or settings.external_api_base_url
    if not base_url:
        base_url = settings.protheus_base_url
    if not base_url:
        raise ServiceUnavailable("EXTERNAL_API_BASE_URL is required when DATA_MODE=external_api")

    auth_type = (_as_optional_string(tenant_raw.get("auth_type")) or settings.external_api_auth_type).lower()
    if auth_type not in {"none", "bearer", "basic"}:
        raise ServiceUnavailable("EXTERNAL_API_AUTH_TYPE must be one of: none, bearer, basic")

    timeout_raw = tenant_raw.get("timeout_seconds", settings.external_api_timeout_seconds)
    try:
        timeout_seconds = float(timeout_raw)
    except (TypeError, ValueError) as exc:
        raise ServiceUnavailable("Invalid timeout_seconds in EXTERNAL_API_TENANT_CONFIGS") from exc
    if timeout_seconds <= 0:
        raise ServiceUnavailable("external API timeout must be greater than zero")

    return ExternalApiTenantConfig(
        base_url=base_url,
        provider_search_path=_as_string(
            tenant_raw.get("provider_search_path"),
            settings.external_api_provider_search_path,
        ),
        auth_type=auth_type,
        token=_as_optional_string(tenant_raw.get("token")) or settings.external_api_token,
        username=_as_optional_string(tenant_raw.get("username")) or settings.external_api_username,
        password=_as_optional_string(tenant_raw.get("password")) or settings.external_api_password,
        timeout_seconds=timeout_seconds,
    )


def build_external_api_auth(
    config: ExternalApiTenantConfig,
    headers: dict[str, str],
) -> httpx.BasicAuth | None:
    if config.auth_type == "none":
        return None
    if config.auth_type == "bearer":
        if not config.token:
            raise ServiceUnavailable("EXTERNAL_API_TOKEN is required when EXTERNAL_API_AUTH_TYPE=bearer")
        headers["Authorization"] = f"Bearer {config.token}"
        return None

    if not config.username or not config.password:
        raise ServiceUnavailable("EXTERNAL_API_USERNAME and EXTERNAL_API_PASSWORD are required for basic auth")
    return httpx.BasicAuth(config.username, config.password)


def _as_string(value: Any, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _as_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
