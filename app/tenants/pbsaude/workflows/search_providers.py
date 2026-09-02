import asyncio
from typing import NoReturn

from ....config import Settings
from ....logging import get_logger
from ....utils.enums import CallFinalState
from ..catalog import get_specialty_catalog
from ..contracts import SearchProvidersRequest, SearchProvidersResponse
from ..integration.client import BusinessRuleError, ServiceUnavailable, get_data_provider
from ..integration.translator import normalize_cpf
from ..mappings import TOOL_SEARCH_PROVIDERS, mask_cpf
from ..provider_policy import (
    ProviderPolicyApplication,
    apply_provider_policy,
    apply_provider_policy_business_override,
)
from ..slot_guard import reopen_slot_collection, validate_search_slot_provenance, recovery_attempt, clear_recovery_attempts

log = get_logger()


async def search_providers(args: dict, settings: Settings, call_id: str, tenant_id: str) -> tuple[dict, CallFinalState]:
    try:
        return await _search_providers(args, settings, call_id, tenant_id)
    except BusinessRuleError as exc:
        if settings.vapi_slot_guard_enabled:
            exc.attempt = recovery_attempt(settings=settings, tenant_id=tenant_id, call_id=call_id,
                                           field=exc.field, code=exc.code)
        raise


async def _search_providers(
    args: dict,
    settings: Settings,
    call_id: str,
    tenant_id: str,
) -> tuple[dict, CallFinalState]:
    provider = get_data_provider(settings)
    payload = SearchProvidersRequest(**args, call_id=call_id, to_number=None)
    catalog = get_specialty_catalog(settings)
    validate_search_slot_provenance(
        settings=settings,
        tenant_id=tenant_id,
        call_id=call_id,
        cpf=payload.cpf,
        city=payload.city,
        query=payload.query,
        catalog=catalog,
    )
    if not normalize_cpf(payload.cpf or ""):
        raise BusinessRuleError(
            code="CPF_INVALIDO",
            field="cpf",
            message="CPF deve conter 11 digitos",
        )
    if not payload.city:
        raise BusinessRuleError(
            code="CIDADE_INVALIDA",
            field="cidade",
            message="Cidade obrigatoria para busca de rede",
            details={"recovery_action": "collect_cidade"},
        )
    if not payload.query:
        raise BusinessRuleError(
            code="ESPECIALIDADE_INVALIDA",
            field="especialidade",
            message="Especialidade obrigatoria para busca de rede",
            details={"recovery_action": "collect_especialidade"},
        )
    if catalog.is_enabled:
        canonical_specialty = catalog.resolve(payload.query)
        if canonical_specialty is None:
            suggestions = catalog.suggest(payload.query)
            raise BusinessRuleError(
                code="ESPECIALIDADE_INVALIDA",
                field="especialidade",
                message="Especialidade nao encontrada na lista disponivel",
                details={"suggestions": suggestions, "recovery_action": "collect_especialidade"},
            )
    else:
        canonical_specialty = payload.query

    policy_application: ProviderPolicyApplication
    business_override_code: str | None = None
    try:
        providers = await asyncio.wait_for(
            asyncio.to_thread(
                provider.search_providers,
                tenant_id,
                call_id,
                payload.city,
                canonical_specialty,
                payload.cpf,
                payload.tipo_atendimento,
            ),
            timeout=min(
                settings.provider_timeout_seconds,
                settings.external_api_total_deadline_seconds,
            ),
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError("Timeout na busca de rede") from exc
    except BusinessRuleError as exc:
        exc = _apply_business_recovery(
            exc,
            settings=settings,
            tenant_id=tenant_id,
            call_id=call_id,
        )
        policy_application = _apply_business_override(
            settings=settings,
            tenant_id=tenant_id,
            call_id=call_id,
            city=payload.city,
            query=payload.query,
            business_error=exc,
        )
        if not policy_application.applied:
            raise exc
        providers = policy_application.providers
        business_override_code = exc.code
    except ServiceUnavailable as exc:
        raise RuntimeError(str(exc)) from exc
    else:
        try:
            policy_application = apply_provider_policy(
                providers,
                tenant_id=tenant_id,
                city=payload.city,
                query=payload.query,
                max_results=settings.provider_max_results,
                enabled=settings.pbsaude_provider_policy_enabled,
            )
        except (OSError, ValueError) as exc:
            _raise_invalid_policy(exc, tenant_id=tenant_id, call_id=call_id, city=payload.city)
        providers = policy_application.providers

    if business_override_code is not None:
        log.warning(
            "provider_policy_business_override",
            event_type="provider_policy",
            tenant_id=tenant_id,
            call_id=call_id,
            policy_version=policy_application.policy_version,
            city_key=policy_application.city_key,
            mode=policy_application.mode,
            matched_service=policy_application.matched_service,
            upstream_code=business_override_code,
            fallback_count=policy_application.fallback_count,
            online_count=policy_application.online_count,
            final_count=len(providers),
            tool_name=TOOL_SEARCH_PROVIDERS,
        )

    if policy_application.evaluated:
        log.info(
            "provider_policy_evaluated",
            event_type="provider_policy",
            tenant_id=tenant_id,
            call_id=call_id,
            policy_version=policy_application.policy_version,
            city_key=policy_application.city_key,
            mode=policy_application.mode,
            matched_service=policy_application.matched_service,
            applied=policy_application.applied,
            upstream_count=policy_application.upstream_count,
            curated_count=policy_application.curated_count,
            fallback_count=policy_application.fallback_count,
            online_count=policy_application.online_count,
            final_count=len(providers),
            tool_name=TOOL_SEARCH_PROVIDERS,
        )

    log.info(
        "provider_search_ok",
        event_type="provider_search",
        tenant_id=tenant_id,
        call_id=call_id,
        city=payload.city,
        legacy_neighborhood_received=payload.neighborhood is not None,
        query=canonical_specialty,
        cpf_mask=mask_cpf(payload.cpf) if payload.cpf else None,
        count=len(providers),
        tool_name=TOOL_SEARCH_PROVIDERS,
        final_state=CallFinalState.RESOLVIDA_AUTOMATICO,
    )
    clear_recovery_attempts(settings=settings, tenant_id=tenant_id, call_id=call_id,
                            cpf=payload.cpf, city=payload.city, query=payload.query, catalog=catalog)
    response = SearchProvidersResponse(providers=list(providers))
    return response.model_dump(), CallFinalState.RESOLVIDA_AUTOMATICO


def _apply_business_override(
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
    city: str,
    query: str,
    business_error: BusinessRuleError,
) -> ProviderPolicyApplication:
    try:
        return apply_provider_policy_business_override(
            tenant_id=tenant_id,
            city=city,
            query=query,
            business_error_code=business_error.code,
            max_results=settings.provider_max_results,
            policy_enabled=settings.pbsaude_provider_policy_enabled,
            business_override_enabled=(
                settings.pbsaude_provider_policy_business_override_enabled
            ),
        )
    except (OSError, ValueError) as exc:
        _raise_invalid_policy(exc, tenant_id=tenant_id, call_id=call_id, city=city)


def _apply_business_recovery(
    error: BusinessRuleError,
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
) -> BusinessRuleError:
    if error.code == "CIDADE_SEM_COBERTURA":
        return BusinessRuleError(
            code=error.code,
            field=None,
            message=error.message,
            details={**error.details, "recovery_action": "offer_handoff"},
            retryable=False,
            handoff_after_retry=False,
        )
    if error.code == "CIDADE_INVALIDA":
        reopen_slot_collection(
            settings=settings,
            tenant_id=tenant_id,
            call_id=call_id,
            field="cidade",
        )
        return BusinessRuleError(
            code=error.code,
            field="cidade",
            message=error.message,
            details={**error.details, "recovery_action": "collect_cidade"},
            retryable=True,
            handoff_after_retry=True,
        )
    if error.code == "ESPECIALIDADE_INVALIDA":
        reopen_slot_collection(
            settings=settings,
            tenant_id=tenant_id,
            call_id=call_id,
            field="especialidade",
        )
        return BusinessRuleError(
            code=error.code,
            field="especialidade",
            message=error.message,
            details={**error.details, "recovery_action": "collect_especialidade"},
            retryable=True,
            handoff_after_retry=True,
        )
    return error


def _raise_invalid_policy(
    exc: Exception,
    *,
    tenant_id: str,
    call_id: str,
    city: str,
) -> NoReturn:
    log.exception(
        "provider_policy_invalid",
        event_type="provider_policy",
        tenant_id=tenant_id,
        call_id=call_id,
        city=city,
        tool_name=TOOL_SEARCH_PROVIDERS,
    )
    raise RuntimeError("Configuracao da politica de rede invalida") from exc
