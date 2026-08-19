import asyncio

from ....config import Settings
from ....logging import get_logger
from ....utils.enums import CallFinalState
from ..contracts import AuthorizationStatusRequest, AuthorizationStatusResponse
from ..integration.client import ServiceUnavailable, get_data_provider
from ..mappings import TOOL_GET_AUTHORIZATION_STATUS

log = get_logger()


async def get_authorization_status(
    args: dict,
    settings: Settings,
    call_id: str,
    tenant_id: str,
) -> tuple[dict, CallFinalState]:
    provider = get_data_provider(settings)
    payload = AuthorizationStatusRequest(**args, call_id=call_id, to_number=None)
    try:
        status_value = await asyncio.wait_for(
            asyncio.to_thread(provider.get_authorization_status, payload.member_id, payload.guia_id),
            timeout=settings.status_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError("Timeout na consulta de guia") from exc
    except ServiceUnavailable as exc:
        raise RuntimeError(str(exc)) from exc

    log.info(
        "authorization_status_ok",
        event_type="authorization_status",
        tenant_id=tenant_id,
        call_id=call_id,
        member_id=payload.member_id,
        guia_id=payload.guia_id,
        status=status_value,
        tool_name=TOOL_GET_AUTHORIZATION_STATUS,
        final_state=CallFinalState.RESOLVIDA_AUTOMATICO,
    )
    response = AuthorizationStatusResponse(status=status_value)
    return response.model_dump(), CallFinalState.RESOLVIDA_AUTOMATICO
