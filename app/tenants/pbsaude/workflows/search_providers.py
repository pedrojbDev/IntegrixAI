import asyncio

from ....config import Settings
from ....logging import get_logger
from ....utils.enums import CallFinalState
from ..catalog import get_specialty_catalog
from ..contracts import SearchProvidersRequest, SearchProvidersResponse
from ..integration.client import BusinessRuleError, ServiceUnavailable, get_data_provider
from ..integration.translator import normalize_cpf
from ..mappings import TOOL_SEARCH_PROVIDERS, mask_cpf

log = get_logger()


async def search_providers(
    args: dict,
    settings: Settings,
    call_id: str,
    tenant_id: str,
) -> tuple[dict, CallFinalState]:
    provider = get_data_provider(settings)
    payload = SearchProvidersRequest(**args, call_id=call_id, to_number=None)
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
        )
    if not payload.query:
        raise BusinessRuleError(
            code="ESPECIALIDADE_INVALIDA",
            field="especialidade",
            message="Especialidade obrigatoria para busca de rede",
        )
    catalog = get_specialty_catalog(settings)
    if catalog.is_enabled:
        canonical_specialty = catalog.resolve(payload.query)
        if canonical_specialty is None:
            suggestions = catalog.suggest(payload.query)
            raise BusinessRuleError(
                code="ESPECIALIDADE_INVALIDA",
                field="especialidade",
                message="Especialidade nao encontrada na lista disponivel",
                details={"suggestions": suggestions},
            )
    else:
        canonical_specialty = payload.query

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
            timeout=settings.provider_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError("Timeout na busca de rede") from exc
    except BusinessRuleError:
        raise
    except ServiceUnavailable as exc:
        raise RuntimeError(str(exc)) from exc

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
