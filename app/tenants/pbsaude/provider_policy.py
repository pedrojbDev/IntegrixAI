from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import Provider


DEFAULT_POLICY_PATH = Path(__file__).with_name("provider_policy.json")


class ProviderServicePolicy(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    service_mode: Literal["in_person", "online", "hybrid"]

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        aliases = [item.strip() for item in value if item.strip()]
        if len({_lookup_key(item) for item in aliases}) != len(aliases):
            raise ValueError("service aliases must be unique after normalization")
        return aliases


class CuratedProviderPolicy(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    provider_code: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=500)
    neighborhood: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=80)
    services: list[ProviderServicePolicy] = Field(min_length=1, max_length=100)
    priority: int = Field(ge=1, le=1000)
    active: bool = True
    use_as_fallback_when_missing_from_api: bool = False
    information_source: Literal["client_provided"]
    last_verified_at: date | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "provider_code", "address", "neighborhood", "phone")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        aliases = [item.strip() for item in value if item.strip()]
        if len({_lookup_key(item) for item in aliases}) != len(aliases):
            raise ValueError("provider aliases must be unique after normalization")
        return aliases

    @model_validator(mode="after")
    def validate_fallback_data(self) -> "CuratedProviderPolicy":
        if self.use_as_fallback_when_missing_from_api:
            if not self.address or not self.phone or not self.last_verified_at:
                raise ValueError("fallback providers require address, phone and last_verified_at")
        service_names = [_lookup_key(service.name) for service in self.services]
        if len(set(service_names)) != len(service_names):
            raise ValueError("provider service names must be unique")
        return self


class CityProviderPolicy(BaseModel):
    uf: str = Field(pattern=r"^[A-Z]{2}$")
    city: str = Field(min_length=1, max_length=160)
    city_key: str = Field(pattern=r"^[a-z0-9_]+$")
    mode: Literal["exclusive", "priority", "ensure"]
    unmatched_specialty_behavior: Literal["use_api_results"]
    providers: list[CuratedProviderPolicy] = Field(min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_city(self) -> "CityProviderPolicy":
        expected_key = _lookup_key(self.city).replace(" ", "_")
        if self.city_key != expected_key:
            raise ValueError(f"city_key must be {expected_key!r}")
        provider_keys = [item.key for item in self.providers]
        if len(set(provider_keys)) != len(provider_keys):
            raise ValueError("provider keys must be unique per city")
        priorities = [item.priority for item in self.providers if item.active]
        if len(set(priorities)) != len(priorities):
            raise ValueError("active provider priorities must be unique per city")
        return self


class ProviderPolicyConfig(BaseModel):
    policy_version: Literal[2]
    tenant_ids: list[str] = Field(min_length=1, max_length=100)
    business_error_fallback_codes: list[
        Literal["ESPECIALIDADE_INVALIDA", "CIDADE_INVALIDA", "CIDADE_SEM_COBERTURA"]
    ] = Field(min_length=1, max_length=10)
    cities: list[CityProviderPolicy] = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("tenant_ids")
    @classmethod
    def normalize_tenant_ids(cls, value: list[str]) -> list[str]:
        tenant_ids = [item.strip() for item in value if item.strip()]
        if len(set(tenant_ids)) != len(tenant_ids):
            raise ValueError("tenant_ids must be unique")
        return tenant_ids

    @field_validator("business_error_fallback_codes")
    @classmethod
    def validate_business_error_fallback_codes(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("business_error_fallback_codes must be unique")
        return value

    @model_validator(mode="after")
    def validate_cities(self) -> "ProviderPolicyConfig":
        keys = [item.city_key for item in self.cities]
        if len(set(keys)) != len(keys):
            raise ValueError("city_key must be globally unique because the tool request has no UF")
        return self


@dataclass(frozen=True, slots=True)
class ProviderPolicyApplication:
    providers: list[Provider]
    evaluated: bool = False
    applied: bool = False
    policy_version: int | None = None
    city_key: str | None = None
    mode: str | None = None
    matched_service: str | None = None
    upstream_count: int = 0
    curated_count: int = 0
    fallback_count: int = 0
    online_count: int = 0


@lru_cache(maxsize=8)
def load_provider_policy(path: str = str(DEFAULT_POLICY_PATH)) -> ProviderPolicyConfig:
    raw = Path(path).read_text(encoding="utf-8")
    return ProviderPolicyConfig.model_validate_json(raw)


def apply_provider_policy(
    providers: Sequence[Provider],
    *,
    tenant_id: str,
    city: str,
    query: str,
    max_results: int,
    enabled: bool,
    config: ProviderPolicyConfig | None = None,
) -> ProviderPolicyApplication:
    upstream = list(providers)
    if not enabled:
        return ProviderPolicyApplication(providers=upstream, upstream_count=len(upstream))

    active_config = config or load_provider_policy()
    if tenant_id not in active_config.tenant_ids:
        return ProviderPolicyApplication(providers=upstream, upstream_count=len(upstream))

    city_key = _lookup_key(city).replace(" ", "_")
    city_policy = next((item for item in active_config.cities if item.city_key == city_key), None)
    if city_policy is None:
        return ProviderPolicyApplication(
            providers=upstream,
            evaluated=True,
            policy_version=active_config.policy_version,
            city_key=city_key,
            upstream_count=len(upstream),
        )

    matches: list[tuple[CuratedProviderPolicy, ProviderServicePolicy]] = []
    for provider_policy in sorted(city_policy.providers, key=lambda item: item.priority):
        if not provider_policy.active:
            continue
        service = _best_matching_service(query, provider_policy.services)
        if service is not None:
            matches.append((provider_policy, service))

    if not matches:
        return ProviderPolicyApplication(
            providers=upstream,
            evaluated=True,
            policy_version=active_config.policy_version,
            city_key=city_policy.city_key,
            mode=city_policy.mode,
            upstream_count=len(upstream),
        )

    curated: list[Provider] = []
    fallback_count = 0
    used_upstream_indexes: set[int] = set()
    for provider_policy, service in matches:
        match = _find_upstream_provider(upstream, provider_policy, used_upstream_indexes)
        if match is not None:
            index, upstream_provider = match
            used_upstream_indexes.add(index)
            curated.append(_decorate_provider(upstream_provider, service))
        elif provider_policy.use_as_fallback_when_missing_from_api:
            curated.append(_fallback_provider(provider_policy, service, city_policy.city))
            fallback_count += 1

    if city_policy.mode == "exclusive":
        final = _deduplicate(curated)[:max_results]
    elif city_policy.mode == "priority":
        final = _deduplicate([*curated, *upstream])[:max_results]
    else:
        final = _ensure_curated(upstream, curated, max_results=max_results)

    return ProviderPolicyApplication(
        providers=final,
        evaluated=True,
        applied=True,
        policy_version=active_config.policy_version,
        city_key=city_policy.city_key,
        mode=city_policy.mode,
        matched_service=matches[0][1].name,
        upstream_count=len(upstream),
        curated_count=len(curated),
        fallback_count=fallback_count,
        online_count=sum(item.service_mode == "online" for item in final),
    )


def apply_provider_policy_business_override(
    *,
    tenant_id: str,
    city: str,
    query: str,
    business_error_code: str,
    max_results: int,
    policy_enabled: bool,
    business_override_enabled: bool,
    config: ProviderPolicyConfig | None = None,
) -> ProviderPolicyApplication:
    if not policy_enabled or not business_override_enabled:
        return ProviderPolicyApplication(providers=[])

    active_config = config or load_provider_policy()
    if business_error_code not in active_config.business_error_fallback_codes:
        return ProviderPolicyApplication(providers=[])

    application = apply_provider_policy(
        [],
        tenant_id=tenant_id,
        city=city,
        query=query,
        max_results=max_results,
        enabled=True,
        config=active_config,
    )
    if not application.applied or application.fallback_count == 0:
        return ProviderPolicyApplication(
            providers=[],
            evaluated=application.evaluated,
            policy_version=application.policy_version,
            city_key=application.city_key,
            mode=application.mode,
            matched_service=application.matched_service,
        )
    return application


def _best_matching_service(
    query: str,
    services: Sequence[ProviderServicePolicy],
) -> ProviderServicePolicy | None:
    query_key = _lookup_key(query)
    scored: list[tuple[int, int, ProviderServicePolicy]] = []
    for index, service in enumerate(services):
        terms = (service.name, *service.aliases)
        scores = [_match_score(query_key, _lookup_key(term)) for term in terms]
        valid_scores = [score for score in scores if score is not None]
        if valid_scores:
            scored.append((min(valid_scores), index, service))
    if not scored:
        return None
    return min(scored, key=lambda item: (item[0], item[1]))[2]


def _match_score(query_key: str, service_key: str) -> int | None:
    if not query_key or not service_key:
        return None
    if query_key == service_key:
        return 0
    padded_query = f" {query_key} "
    padded_service = f" {service_key} "
    if padded_query in padded_service:
        return 1
    if padded_service in padded_query:
        return 2
    return None


def _find_upstream_provider(
    upstream: Sequence[Provider],
    policy: CuratedProviderPolicy,
    used_indexes: set[int],
) -> tuple[int, Provider] | None:
    identity_names = {_lookup_key(policy.name), *(_lookup_key(item) for item in policy.aliases)}
    for index, provider in enumerate(upstream):
        if index in used_indexes:
            continue
        if policy.provider_code and provider.provider_code == policy.provider_code:
            return index, provider
        if _lookup_key(provider.name) in identity_names:
            return index, provider
    return None


def _decorate_provider(provider: Provider, service: ProviderServicePolicy) -> Provider:
    updates: dict[str, object] = {
        "specialty": service.name,
        "service_mode": service.service_mode,
    }
    if service.service_mode == "online":
        updates.update(address="", neighborhood=None)
    return provider.model_copy(update=updates)


def _fallback_provider(
    policy: CuratedProviderPolicy,
    service: ProviderServicePolicy,
    city: str,
) -> Provider:
    online = service.service_mode == "online"
    return Provider(
        name=policy.name,
        specialty=service.name,
        address="" if online else policy.address or "",
        city=city,
        neighborhood=None if online else policy.neighborhood,
        phone=policy.phone or "Não informado",
        service_mode=service.service_mode,
        provider_code=policy.provider_code,
    )


def _ensure_curated(
    upstream: Sequence[Provider],
    curated: Sequence[Provider],
    *,
    max_results: int,
) -> list[Provider]:
    final = _deduplicate(upstream)
    curated_by_key = {_provider_key(item): item for item in curated}
    for index, provider in enumerate(final):
        replacement = curated_by_key.pop(_provider_key(provider), None)
        if replacement is not None:
            final[index] = replacement
    final.extend(curated_by_key.values())
    final = _deduplicate(final)

    protected = {_provider_key(item) for item in curated}
    while len(final) > max_results:
        removable = next(
            (index for index in range(len(final) - 1, -1, -1) if _provider_key(final[index]) not in protected),
            None,
        )
        if removable is None:
            return list(curated)[:max_results]
        final.pop(removable)
    return final


def _deduplicate(providers: Sequence[Provider]) -> list[Provider]:
    seen: set[str] = set()
    output: list[Provider] = []
    for provider in providers:
        key = _provider_key(provider)
        if key in seen:
            continue
        seen.add(key)
        output.append(provider)
    return output


def _provider_key(provider: Provider) -> str:
    if provider.provider_code:
        return f"code:{provider.provider_code.strip().lower()}"
    return f"name:{_lookup_key(provider.name)}"


def _lookup_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).split())
