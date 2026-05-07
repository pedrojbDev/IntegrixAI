import asyncio

from ....config import Settings
from ....logging import get_logger
from ....utils.enums import CallFinalState
from ..contracts import AuthenticateRequest, AuthenticateResponse
from ..integration.client import AuthenticationError, ServiceUnavailable, get_data_provider
from ..mappings import TOOL_AUTHENTICATE_MEMBER, mask_cpf

log = get_logger()


async def authenticate_member(
    args: dict,
    settings: Settings,
    call_id: str,
    tenant_id: str,
) -> tuple[dict, CallFinalState]:
    provider = get_data_provider(settings)
    payload = AuthenticateRequest(**args, call_id=call_id, to_number=None)
    try:
        member_id, auth_level = await asyncio.wait_for(
            asyncio.to_thread(provider.authenticate_member, payload.cpf, payload.birthdate, call_id),
            timeout=settings.auth_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError("Timeout na autenticacao") from exc
    except AuthenticationError as exc:
        log.warning(
            "auth_failed",
            event_type="auth_failed",
            tenant_id=tenant_id,
            call_id=call_id,
            cpf_mask=mask_cpf(payload.cpf),
            reason=str(exc),
            tool_name=TOOL_AUTHENTICATE_MEMBER,
        )
        raise ValueError("Autenticacao nao concluida") from exc
    except ServiceUnavailable as exc:
        raise RuntimeError(str(exc)) from exc

    log.info(
        "auth_success",
        event_type="auth_success",
        tenant_id=tenant_id,
        call_id=call_id,
        member_id=member_id,
        auth_level=auth_level,
        tool_name=TOOL_AUTHENTICATE_MEMBER,
        final_state=CallFinalState.RESOLVIDA_AUTOMATICO,
    )
    response = AuthenticateResponse(member_id=member_id, auth_level=auth_level)
    return response.model_dump(), CallFinalState.RESOLVIDA_AUTOMATICO
