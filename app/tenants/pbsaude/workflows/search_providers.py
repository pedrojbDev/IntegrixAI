import asyncio
import json
from typing import NoReturn

from pydantic import ValidationError

from ....config import Settings
from ....logging import get_logger
from ....core.tools.exceptions import UpstreamToolError
from ....utils.enums import CallFinalState
from ..catalog import get_specialty_catalog
from ..search_execution import execute_search
from ..search_events import persist_search_event
from ....platform.services.vapi_conversation import normalize_text
from ..contracts import SearchProvidersRequest, SearchProvidersResponse
from ..integration.client import BusinessRuleError, ServiceUnavailable, get_data_provider
from ..integration.translator import normalize_cpf
from ..mappings import TOOL_SEARCH_PROVIDERS, mask_cpf
from ..provider_policy import (
    ProviderPolicyApplication,
    apply_provider_policy,
    apply_provider_policy_business_override,
)
from ..slot_guard import (
    clear_recovery_attempts,
    enforce_recovery_gate,
    recovery_attempt,
    reopen_slot_collection,
    validate_search_slot_provenance,
)

log = get_logger()


async def search_providers(args: dict, settings: Settings, call_id: str, tenant_id: str) -> tuple[dict, CallFinalState]:
    try:
        worker = asyncio.ensure_future(asyncio.to_thread(_search_providers, args, settings, call_id, tenant_id))
        # Shield the synchronous owner: cancelling a request cannot stop its HTTP
        # thread or release the database search lock early.
        worker.add_done_callback(_consume_worker_exception)
        try:
            return await asyncio.wait_for(asyncio.shield(worker), timeout=min(
                settings.provider_timeout_seconds, settings.external_api_total_deadline_seconds))
        except asyncio.TimeoutError as exc:
            error = TimeoutError("Timeout na busca de rede")
            _persist_failure_events(settings, tenant_id, call_id, error)
            error._search_event_recorded = True
            raise error from exc
    except BusinessRuleError as exc:
        if (
            settings.vapi_slot_guard_enabled
            and not settings.pbsaude_vapi_recovery_gate_enabled
            and not getattr(exc, "_vapi_recovery_applied", False)
        ):
            # Preserve the established guard behavior when the new authoritative
            # recovery gate remains opt-in.
            exc.attempt = recovery_attempt(
                settings=settings,
                tenant_id=tenant_id,
                call_id=call_id,
                field=exc.field,
                code=exc.code,
            )
        raise


def _consume_worker_exception(worker):
    if not worker.cancelled():
        worker.exception()


def _rejected_value(args: dict, field: str | None) -> str | None:
    if field == "cpf":
        value = args.get("cpf")
    elif field == "cidade":
        value = args.get("city", args.get("cidade"))
    elif field == "especialidade":
        value = args.get("query", args.get("especialidade"))
    else:
        value = None
    return str(value) if value is not None else None


def _technical_upstream_code(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "UPSTREAM_TIMEOUT"
    if isinstance(exc, UpstreamToolError):
        return exc.upstream_code
    if isinstance(exc, ConnectionError):
        return "UPSTREAM_NETWORK"
    return "UPSTREAM_UNEXPECTED"


def _persist_failure_events(settings: Settings, tenant_id: str, call_id: str, exc: BaseException) -> None:
    upstream_code = _technical_upstream_code(exc)
    persist_search_event(
        settings=settings,
        tenant_id=tenant_id,
        call_id=call_id,
        event_type="provider_search_failed",
        ok=False,
        final_state=CallFinalState.EM_ANDAMENTO,
        error_code=upstream_code,
        payload={
            "upstream_code": upstream_code,
            "recovery_action": "offer_handoff",
        },
    )
    _persist_handoff_recommended(settings, tenant_id, call_id, upstream_code)


def _persist_handoff_recommended(settings: Settings, tenant_id: str, call_id: str,
                                 upstream_code: str) -> None:
    persist_search_event(
        settings=settings,
        tenant_id=tenant_id,
        call_id=call_id,
        event_type="provider_handoff_recommended",
        ok=False,
        final_state=CallFinalState.EM_ANDAMENTO,
        error_code=upstream_code,
        payload={
            "upstream_code": upstream_code,
            "recovery_action": "offer_handoff",
        },
    )


def _validated_payload(args: dict, call_id: str) -> SearchProvidersRequest:
    try:
        return SearchProvidersRequest(**args, call_id=call_id, to_number=None)
    except ValidationError as exc:
        locations = {str(item) for error in exc.errors() for item in error.get("loc", ())}
        if locations & {"query", "especialidade"}:
            raise BusinessRuleError(
                code="ESPECIALIDADE_INVALIDA",
                field="especialidade",
                message="Especialidade obrigatoria para busca de rede",
                details={"recovery_action": "collect_especialidade"},
            ) from exc
        if locations & {"city", "cidade"}:
            raise BusinessRuleError(
                code="CIDADE_INVALIDA",
                field="cidade",
                message="Cidade obrigatoria para busca de rede",
                details={"recovery_action": "collect_cidade"},
            ) from exc
        raise


def _search_providers(
    args: dict,
    settings: Settings,
    call_id: str,
    tenant_id: str,
) -> tuple[dict, CallFinalState]:
    persist_search_event(
        settings=settings,
        tenant_id=tenant_id,
        call_id=call_id,
        event_type="provider_search_requested",
    )
    try:
        return _search_providers_impl(args, settings, call_id, tenant_id)
    except BusinessRuleError as exc:
        error = exc
        if (
            settings.pbsaude_vapi_recovery_gate_enabled
            and error.field in {"cpf", "cidade", "especialidade"}
            and error.code != "USER_TURN_REQUIRED"
            and not getattr(error, "_vapi_recovery_applied", False)
        ):
            if error.code != "SLOT_UNCONFIRMED":
                error = _apply_business_recovery(
                    error,
                    settings=settings,
                    tenant_id=tenant_id,
                    call_id=call_id,
                )
            error.attempt = recovery_attempt(
                settings=settings,
                tenant_id=tenant_id,
                call_id=call_id,
                field=error.field,
                code=error.code,
                rejected_value=_rejected_value(args, error.field),
            )
            error._vapi_recovery_applied = True
        action = (error.details or {}).get("recovery_action")
        event_type = "provider_search_failed" if action == "offer_handoff" else "provider_search_blocked"
        persist_search_event(
            settings=settings,
            tenant_id=tenant_id,
            call_id=call_id,
            event_type=event_type,
            ok=False,
            final_state=CallFinalState.EM_ANDAMENTO,
            error_code=error.code,
            payload={
                "upstream_code": error.code,
                "recovery_action": action,
                "attempt": error.attempt,
            },
        )
        if action == "offer_handoff" or (
            error.handoff_after_retry and (error.attempt or 0) >= 2
        ):
            _persist_handoff_recommended(settings, tenant_id, call_id, error.code)
        if error is exc:
            raise
        raise error from exc
    except BaseException as exc:
        if not getattr(exc, "_search_event_recorded", False):
            _persist_failure_events(settings, tenant_id, call_id, exc)
            try:
                exc._search_event_recorded = True
            except (AttributeError, TypeError):
                pass
        raise


def _search_providers_impl(
    args: dict,
    settings: Settings,
    call_id: str,
    tenant_id: str,
) -> tuple[dict, CallFinalState]:
    payload = _validated_payload(args, call_id)
    enforce_recovery_gate(
        settings=settings,
        tenant_id=tenant_id,
        call_id=call_id,
        cpf=payload.cpf,
        city=payload.city,
        query=payload.query,
    )
    provider = get_data_provider(settings)
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
            clarification = {}
            if normalize_text(payload.query) == 'exame de vista':
                clarification['clarification_question'] = (
                    'Voce procura uma consulta com oftalmologista ou um exame especifico? Qual exame?')
            raise BusinessRuleError(
                code="ESPECIALIDADE_INVALIDA",
                field="especialidade",
                message="Especialidade nao encontrada na lista disponivel",
                details={"suggestions": suggestions, "recovery_action": "collect_especialidade", **clarification},
            )
    else:
        canonical_specialty = payload.query

    def validate(session):
        validate_search_slot_provenance(settings=settings, tenant_id=tenant_id, call_id=call_id,
            cpf=payload.cpf, city=payload.city, query=payload.query, catalog=catalog, session=session)

    def execute():
        return _execute_provider_search(payload, settings, call_id, tenant_id, provider, canonical_specialty)

    def complete(session):
        clear_recovery_attempts(settings=settings, tenant_id=tenant_id, call_id=call_id,
            cpf=payload.cpf, city=payload.city, query=payload.query, catalog=catalog, session=session)

    def recover(error, session, discarded):
        if discarded:
            error.attempt = 0
        else:
            error = _apply_business_recovery(error, settings=settings, tenant_id=tenant_id,
                                             call_id=call_id, session=session)
            error.attempt = recovery_attempt(settings=settings, tenant_id=tenant_id, call_id=call_id,
                                            field=error.field, code=error.code,
                                            rejected_value=_rejected_value(args, error.field), session=session)
        # The async caller must not count this error again against a newer turn.
        error._vapi_recovery_applied = True
        return error

    if settings.vapi_slot_guard_enabled:
        signature = json.dumps([normalize_cpf(payload.cpf or ""), normalize_text(payload.city),
                                normalize_text(canonical_specialty), payload.tipo_atendimento], ensure_ascii=True)
        result = execute_search(settings=settings, tenant_id=tenant_id, call_id=call_id,
                                signature=signature, validate=validate, execute=execute,
                                complete=complete, recover=recover,
                                emit=lambda session, event_type, **kwargs: persist_search_event(
                                    settings=settings,
                                    tenant_id=tenant_id,
                                    call_id=call_id,
                                    event_type=event_type,
                                    session=session,
                                    **kwargs,
                                ))
    else:
        persist_search_event(
            settings=settings,
            tenant_id=tenant_id,
            call_id=call_id,
            event_type="provider_search_upstream_started",
        )
        try:
            result = execute()
        except BusinessRuleError as exc:
            raise _apply_business_recovery(exc, settings=settings, tenant_id=tenant_id, call_id=call_id)
        persist_search_event(
            settings=settings,
            tenant_id=tenant_id,
            call_id=call_id,
            event_type="provider_search_completed",
            ok=True,
            final_state=result[1],
            payload={"provider_count": len((result[0] or {}).get("providers", []))},
        )
    return result


def _execute_provider_search(payload, settings, call_id, tenant_id, provider, canonical_specialty):
    policy_application: ProviderPolicyApplication
    business_override_code: str | None = None
    try:
        providers = provider.search_providers(tenant_id, call_id, payload.city,
            canonical_specialty, payload.cpf, payload.tipo_atendimento)
    except BusinessRuleError as exc:
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
        raise UpstreamToolError(str(exc), exc.upstream_code) from exc
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
    session=None,
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
            session=session,
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
            session=session,
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
