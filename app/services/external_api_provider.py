from dataclasses import dataclass
from datetime import date
import re
from typing import Any, Sequence

import httpx
from fastapi import HTTPException

from ..config import Settings
from ..schemas.tools import Provider
from ..utils.chaos import maybe_introduce_chaos
from ..utils.enums import AuthLevel, AuthorizationStatus
from .data_provider import BusinessRuleError, DataProvider, ServiceUnavailable


@dataclass(slots=True)
class ExternalApiTenantConfig:
    base_url: str
    provider_search_path: str
    auth_type: str
    token: str | None
    username: str | None
    password: str | None
    timeout_seconds: float


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
        city: str,
        neighborhood: str | None,
        query: str,
        cpf: str | None,
        tipo_atendimento: str | None,
    ) -> Sequence[Provider]:
        try:
            maybe_introduce_chaos(self.settings)
        except HTTPException as exc:
            raise ServiceUnavailable(str(exc.detail)) from exc

        cpf_normalized = self._normalize_cpf(cpf or "")
        if not cpf_normalized:
            raise BusinessRuleError(
                code="CPF_INVALIDO",
                field="cpf",
                message="CPF deve conter 11 digitos",
            )

        config = self._resolve_tenant_config(tenant_id)
        payload: dict[str, Any] = {
            "cpf": cpf_normalized,
            "especialidade": query.strip(),
            "cidade": city.strip(),
            "bairro": (neighborhood or "").strip(),
        }
        if tipo_atendimento and tipo_atendimento.strip():
            payload["tipoAtendimento"] = tipo_atendimento.strip()

        headers: dict[str, str] = {}
        auth = self._build_auth(config, headers)
        url = self._build_url(config.base_url, config.provider_search_path)

        try:
            with httpx.Client(timeout=config.timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers, auth=auth)
        except httpx.TimeoutException as exc:
            raise TimeoutError("Timeout na consulta da API externa de rede") from exc
        except httpx.RequestError as exc:
            raise ServiceUnavailable("Falha de comunicacao com API externa") from exc

        data = self._parse_json(response)
        if response.status_code in (401, 403):
            raise ServiceUnavailable("Falha de autenticacao na API externa")
        if response.status_code >= 500:
            raise ServiceUnavailable("API externa indisponivel")
        if response.status_code >= 400:
            if self._is_business_error(data):
                raise BusinessRuleError(
                    code=self._as_string(data.get("errorCode"), "BUSINESS_ERROR"),
                    field=self._as_optional_string(data.get("field")),
                    message=self._as_string(data.get("message"), "Nao foi possivel concluir a busca da rede"),
                )
            raise ServiceUnavailable(f"API externa retornou HTTP {response.status_code}")

        if self._is_success(data):
            return self._normalize_providers(
                data,
                city=city,
                query=query,
                max_results=self.settings.provider_max_results,
            )

        if self._is_business_error(data):
            raise BusinessRuleError(
                code=self._as_string(data.get("errorCode"), "BUSINESS_ERROR"),
                field=self._as_optional_string(data.get("field")),
                message=self._as_string(data.get("message"), "Nao foi possivel concluir a busca da rede"),
            )

        raise ServiceUnavailable("Resposta inesperada da API externa")

    def _resolve_tenant_config(self, tenant_id: str) -> ExternalApiTenantConfig:
        tenant_raw = self.settings.external_api_tenant_configs.get(tenant_id) or {}

        base_url = self._as_optional_string(tenant_raw.get("base_url")) or self.settings.external_api_base_url
        if not base_url:
            base_url = self.settings.protheus_base_url
        if not base_url:
            raise ServiceUnavailable("EXTERNAL_API_BASE_URL is required when DATA_MODE=external_api")

        auth_type = (
            self._as_optional_string(tenant_raw.get("auth_type")) or self.settings.external_api_auth_type
        ).lower()
        if auth_type not in {"none", "bearer", "basic"}:
            raise ServiceUnavailable("EXTERNAL_API_AUTH_TYPE must be one of: none, bearer, basic")

        timeout_raw = tenant_raw.get("timeout_seconds", self.settings.external_api_timeout_seconds)
        try:
            timeout_seconds = float(timeout_raw)
        except (TypeError, ValueError) as exc:
            raise ServiceUnavailable("Invalid timeout_seconds in EXTERNAL_API_TENANT_CONFIGS") from exc
        if timeout_seconds <= 0:
            raise ServiceUnavailable("external API timeout must be greater than zero")

        return ExternalApiTenantConfig(
            base_url=base_url,
            provider_search_path=self._as_string(
                tenant_raw.get("provider_search_path"),
                self.settings.external_api_provider_search_path,
            ),
            auth_type=auth_type,
            token=self._as_optional_string(tenant_raw.get("token")) or self.settings.external_api_token,
            username=self._as_optional_string(tenant_raw.get("username")) or self.settings.external_api_username,
            password=self._as_optional_string(tenant_raw.get("password")) or self.settings.external_api_password,
            timeout_seconds=timeout_seconds,
        )

    def _build_auth(
        self, config: ExternalApiTenantConfig, headers: dict[str, str]
    ) -> httpx.BasicAuth | None:
        if config.auth_type == "none":
            return None
        if config.auth_type == "bearer":
            if not config.token:
                raise ServiceUnavailable("EXTERNAL_API_TOKEN is required when EXTERNAL_API_AUTH_TYPE=bearer")
            headers["Authorization"] = f"Bearer {config.token}"
            return None

        if not config.username or not config.password:
            raise ServiceUnavailable(
                "EXTERNAL_API_USERNAME and EXTERNAL_API_PASSWORD are required for basic auth"
            )
        return httpx.BasicAuth(config.username, config.password)

    @staticmethod
    def _build_url(base_url: str, path: str) -> str:
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    @staticmethod
    def _normalize_cpf(cpf: str) -> str | None:
        digits = "".join(ch for ch in cpf if ch.isdigit())
        return digits if len(digits) == 11 else None

    @staticmethod
    def _as_string(value: Any, default: str) -> str:
        text = str(value).strip() if value is not None else ""
        return text or default

    @staticmethod
    def _as_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceUnavailable("Resposta nao JSON da API externa") from exc
        if not isinstance(data, dict):
            raise ServiceUnavailable("Resposta JSON invalida da API externa")
        return data

    @staticmethod
    def _is_success(data: dict[str, Any]) -> bool:
        raw = data.get("success")
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"true", "1", "yes", "ok"}
        return isinstance(data.get("prestadores"), list) and "errorCode" not in data

    @staticmethod
    def _is_business_error(data: dict[str, Any]) -> bool:
        return any(k in data for k in ("errorCode", "field", "message")) and not ExternalApiDataProvider._is_success(
            data
        )

    @staticmethod
    def _normalize_providers(
        data: dict[str, Any],
        *,
        city: str,
        query: str,
        max_results: int,
    ) -> list[Provider]:
        raw_list = data.get("prestadores")
        if not isinstance(raw_list, list):
            return []

        providers: list[Provider] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            name = ExternalApiDataProvider._as_optional_string(item.get("nome") or item.get("name"))
            address = ExternalApiDataProvider._as_optional_string(
                item.get("endereco") or item.get("address")
            )
            if not name or not address:
                continue

            providers.append(
                Provider(
                    name=ExternalApiDataProvider._clean_whitespace(name),
                    specialty=query.strip(),
                    address=ExternalApiDataProvider._clean_whitespace(address),
                    city=ExternalApiDataProvider._clean_whitespace(city.strip()),
                    neighborhood=ExternalApiDataProvider._clean_whitespace(neighborhood_value)
                    if (
                        neighborhood_value := ExternalApiDataProvider._as_optional_string(
                            item.get("bairro") or item.get("neighborhood")
                        )
                    )
                    else None,
                    phone=ExternalApiDataProvider._normalize_phone(
                        ExternalApiDataProvider._as_string(item.get("telefone") or item.get("phone"), "")
                    ),
                )
            )

        return providers[:max_results]

    @staticmethod
    def _clean_whitespace(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _normalize_phone(raw_phone: str) -> str:
        phone = ExternalApiDataProvider._clean_whitespace(raw_phone)
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) == 10:
            return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
        if len(digits) == 11:
            return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
        return phone or "Nao informado"

    def _validate_base_config(self) -> None:
        if self.settings.external_api_tenant_configs:
            return
        if not self.settings.external_api_base_url and not self.settings.protheus_base_url:
            raise ServiceUnavailable("EXTERNAL_API_BASE_URL is required when DATA_MODE=external_api")
