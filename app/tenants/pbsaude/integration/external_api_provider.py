from __future__ import annotations

from datetime import date
from typing import Any, Sequence

import httpx
from fastapi import HTTPException

from ....config import Settings
from ....utils.chaos import maybe_introduce_chaos
from ....utils.enums import AuthLevel, AuthorizationStatus
from ..contracts import Provider
from .auth import build_external_api_auth, resolve_external_api_tenant_config
from .client import BusinessRuleError, DataProvider, ServiceUnavailable
from .http_client import post_json_with_retries
from .translator import (
    as_optional_string,
    as_string,
    is_business_error,
    is_success,
    normalize_cpf,
    normalize_providers,
    parse_external_api_json,
)


class ExternalApiDataProvider(DataProvider):
    """
    Adapter for customer APIs in DATA_MODE=external_api.
    Search providers is implemented for the pilot; other flows stay as placeholders.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._validate_base_config()

    def authenticate_member(self, cpf: str, birthdate: date, call_id: str) -> tuple[str, AuthLevel]:
        raise ServiceUnavailable("External API authenticate_member not implemented")

    def get_authorization_status(self, member_id: str, guia_id: str) -> AuthorizationStatus:
        raise ServiceUnavailable("External API get_authorization_status not implemented")

    def search_providers(
        self,
        tenant_id: str,
        call_id: str,
        city: str,
        query: str,
        cpf: str | None,
        tipo_atendimento: str | None,
    ) -> Sequence[Provider]:
        try:
            maybe_introduce_chaos(self.settings)
        except HTTPException as exc:
            upstream_code = (
                "UPSTREAM_AUTH"
                if exc.status_code in {401, 403}
                else "UPSTREAM_5XX"
                if exc.status_code >= 500
                else "UPSTREAM_UNEXPECTED"
            )
            raise ServiceUnavailable(str(exc.detail), upstream_code) from exc

        cpf_normalized = normalize_cpf(cpf or "")
        if not cpf_normalized:
            raise BusinessRuleError(
                code="CPF_INVALIDO",
                field="cpf",
                message="CPF deve conter 11 digitos",
            )

        config = resolve_external_api_tenant_config(self.settings, tenant_id)
        payload: dict[str, Any] = {
            "cpf": cpf_normalized,
            "especialidade": query.strip(),
            "cidade": city.strip(),
        }
        if tipo_atendimento and tipo_atendimento.strip():
            payload["tipoAtendimento"] = tipo_atendimento.strip()

        headers: dict[str, str] = {}
        auth = build_external_api_auth(config, headers)
        url = self._build_url(config.base_url, config.provider_search_path)

        try:
            response = post_json_with_retries(
                settings=self.settings,
                tenant_id=tenant_id,
                call_id=call_id,
                url=url,
                path=config.provider_search_path,
                payload=payload,
                headers=headers,
                auth=auth,
                timeout_seconds=config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("Timeout na consulta da API externa de rede") from exc
        except httpx.RequestError as exc:
            raise ServiceUnavailable(
                "Falha de comunicacao com API externa",
                "UPSTREAM_NETWORK",
            ) from exc

        if response.status_code in (401, 403):
            raise ServiceUnavailable("Falha de autenticacao na API externa", "UPSTREAM_AUTH")
        if response.status_code >= 500:
            raise ServiceUnavailable("API externa indisponivel", "UPSTREAM_5XX")
        data = parse_external_api_json(response)
        if response.status_code >= 400:
            if is_business_error(data):
                raise BusinessRuleError(
                    code=as_string(data.get("errorCode"), "BUSINESS_ERROR"),
                    field=as_optional_string(data.get("field")),
                    message=as_string(data.get("message"), "Nao foi possivel concluir a busca da rede"),
                )
            raise ServiceUnavailable(
                f"API externa retornou HTTP {response.status_code}",
                "UPSTREAM_UNEXPECTED",
            )

        if is_success(data):
            return normalize_providers(
                data,
                city=city,
                query=query,
                max_results=self.settings.provider_max_results,
            )

        if is_business_error(data):
            raise BusinessRuleError(
                code=as_string(data.get("errorCode"), "BUSINESS_ERROR"),
                field=as_optional_string(data.get("field")),
                message=as_string(data.get("message"), "Nao foi possivel concluir a busca da rede"),
            )

        raise ServiceUnavailable("Resposta inesperada da API externa", "UPSTREAM_UNEXPECTED")

    @staticmethod
    def _build_url(base_url: str, path: str) -> str:
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    def _validate_base_config(self) -> None:
        if self.settings.external_api_tenant_configs:
            return
        if not self.settings.external_api_base_url and not self.settings.protheus_base_url:
            raise ServiceUnavailable("EXTERNAL_API_BASE_URL is required when DATA_MODE=external_api")
