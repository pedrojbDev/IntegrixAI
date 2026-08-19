from __future__ import annotations

import re
from typing import Any

import httpx

from ..contracts import Provider
from .client import ServiceUnavailable
from .speech_text import normalize_provider_address, normalize_provider_speech_text


def as_string(value: Any, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def as_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_external_api_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise ServiceUnavailable("Resposta nao JSON da API externa") from exc
    if not isinstance(data, dict):
        raise ServiceUnavailable("Resposta JSON invalida da API externa")
    return data


def is_success(data: dict[str, Any]) -> bool:
    raw = data.get("success")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes", "ok"}
    return isinstance(data.get("prestadores"), list) and "errorCode" not in data


def is_business_error(data: dict[str, Any]) -> bool:
    return any(key in data for key in ("errorCode", "field", "message")) and not is_success(data)


def normalize_providers(
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
        name = resolve_provider_name(item)
        address = as_optional_string(item.get("endereco") or item.get("address"))
        if not name or not address:
            continue
        neighborhood = as_optional_string(item.get("bairro") or item.get("neighborhood"))
        street_type = as_optional_string(
            item.get("tipoLogradouro")
            or item.get("tipo_logradouro")
            or item.get("streetType")
            or item.get("street_type")
        )

        providers.append(
            Provider(
                name=normalize_provider_speech_text(clean_whitespace(name)),
                specialty=normalize_provider_speech_text(query.strip()),
                address=normalize_provider_address(
                    clean_whitespace(address),
                    street_type=street_type,
                    city=city,
                    neighborhood=neighborhood,
                ),
                city=normalize_provider_speech_text(clean_whitespace(city.strip())),
                neighborhood=normalize_provider_speech_text(clean_whitespace(neighborhood))
                if neighborhood
                else None,
                phone=normalize_phone(as_string(item.get("telefone") or item.get("phone"), "")),
                provider_code=as_optional_string(
                    item.get("codigoPrestador")
                    or item.get("codigo_prestador")
                    or item.get("providerCode")
                    or item.get("provider_code")
                    or item.get("codigo")
                    or item.get("id")
                ),
            )
        )

    return providers[:max_results]


def resolve_provider_name(item: dict[str, Any]) -> str | None:
    for candidate in (
        as_optional_string(item.get("fantasia")),
        as_optional_string(item.get("nome")),
        as_optional_string(item.get("name")),
    ):
        if candidate:
            return candidate
    return None


def clean_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_phone(raw_phone: str) -> str:
    phone = clean_whitespace(raw_phone)
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    return phone or "Não informado"


def normalize_cpf(cpf: str) -> str | None:
    digits = "".join(ch for ch in cpf if ch.isdigit())
    return digits if len(digits) == 11 else None
