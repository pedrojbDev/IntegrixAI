import asyncio
import hmac
import json
import time
import uuid
from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, Body, Request
from pydantic import ValidationError

from ..config import Settings, get_settings
from ..context import clear_call_context, set_call_context
from ..logging import get_logger
from ..schemas.tools import (
    AuthenticateRequest,
    AuthenticateResponse,
    AuthorizationStatusRequest,
    AuthorizationStatusResponse,
    HandoffHumanRequest,
    HandoffHumanResponse,
    SearchProvidersRequest,
    SearchProvidersResponse,
    ToolError,
    ToolResponse,
)
from ..services.data_provider import AuthenticationError, ServiceUnavailable, get_data_provider
from ..services.audit_store import record_call_event
from ..services.metrics import metrics_store
from ..services.tenant import resolve_tenant
from ..utils.enums import CallFinalState

router = APIRouter()
log = get_logger()

ToolHandler = Callable[[dict, Settings, str, str], Awaitable[tuple[dict, CallFinalState]]]


def _mask_cpf(cpf: str) -> str:
    digits = "".join(filter(str.isdigit, cpf))
    return f"***{digits[-4:]}" if digits else "***"


async def _handle_authenticate_member(
    args: dict, settings: Settings, call_id: str, tenant_id: str
) -> tuple[dict, CallFinalState]:
    provider = get_data_provider(settings)
    payload = AuthenticateRequest(**args, call_id=call_id, to_number=None)
    try:
        member_id, auth_level = await asyncio.wait_for(
            asyncio.to_thread(provider.authenticate_member, payload.cpf, payload.birthdate, call_id),
            timeout=settings.auth_timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise TimeoutError("Timeout na autenticacao")
    except AuthenticationError as exc:
        log.warning(
            "auth_failed",
            event_type="auth_failed",
            tenant_id=tenant_id,
            call_id=call_id,
            cpf_mask=_mask_cpf(payload.cpf),
            reason=str(exc),
            tool_name="authenticate_member",
        )
        raise ValueError("Autenticacao nao concluida")
    except ServiceUnavailable as exc:
        raise RuntimeError(str(exc))

    log.info(
        "auth_success",
        event_type="auth_success",
        tenant_id=tenant_id,
        call_id=call_id,
        member_id=member_id,
        auth_level=auth_level,
        tool_name="authenticate_member",
        final_state=CallFinalState.RESOLVIDA_AUTOMATICO,
    )
    resp = AuthenticateResponse(member_id=member_id, auth_level=auth_level)
    return resp.model_dump(), CallFinalState.RESOLVIDA_AUTOMATICO


async def _handle_get_authorization_status(
    args: dict, settings: Settings, call_id: str, tenant_id: str
) -> tuple[dict, CallFinalState]:
    provider = get_data_provider(settings)
    payload = AuthorizationStatusRequest(**args, call_id=call_id, to_number=None)
    try:
        status_value = await asyncio.wait_for(
            asyncio.to_thread(provider.get_authorization_status, payload.member_id, payload.guia_id),
            timeout=settings.status_timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise TimeoutError("Timeout na consulta de guia")
    except ServiceUnavailable as exc:
        raise RuntimeError(str(exc))

    log.info(
        "authorization_status_ok",
        event_type="authorization_status",
        tenant_id=tenant_id,
        call_id=call_id,
        member_id=payload.member_id,
        guia_id=payload.guia_id,
        status=status_value,
        tool_name="get_authorization_status",
        final_state=CallFinalState.RESOLVIDA_AUTOMATICO,
    )
    resp = AuthorizationStatusResponse(status=status_value)
    return resp.model_dump(), CallFinalState.RESOLVIDA_AUTOMATICO


async def _handle_search_providers(
    args: dict, settings: Settings, call_id: str, tenant_id: str
) -> tuple[dict, CallFinalState]:
    provider = get_data_provider(settings)
    payload = SearchProvidersRequest(**args, call_id=call_id, to_number=None)
    try:
        providers = await asyncio.wait_for(
            asyncio.to_thread(provider.search_providers, payload.city, payload.neighborhood, payload.query),
            timeout=settings.provider_timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise TimeoutError("Timeout na busca de rede")
    except ServiceUnavailable as exc:
        raise RuntimeError(str(exc))

    log.info(
        "provider_search_ok",
        event_type="provider_search",
        tenant_id=tenant_id,
        call_id=call_id,
        city=payload.city,
        neighborhood=payload.neighborhood,
        query=payload.query,
        count=len(providers),
        tool_name="search_providers",
        final_state=CallFinalState.RESOLVIDA_AUTOMATICO,
    )
    resp = SearchProvidersResponse(providers=list(providers))
    return resp.model_dump(), CallFinalState.RESOLVIDA_AUTOMATICO


async def _handle_handoff_human(
    args: dict, settings: Settings, call_id: str, tenant_id: str
) -> tuple[dict, CallFinalState]:
    payload = HandoffHumanRequest(**args, call_id=call_id, to_number=None)
    log.info(
        "handoff_human",
        event_type="handoff",
        tenant_id=tenant_id,
        call_id=call_id,
        reason=payload.reason,
        tool_name="handoff_human",
        final_state=CallFinalState.TRANSFERIDA_HUMANO,
    )
    resp = HandoffHumanResponse(status=CallFinalState.TRANSFERIDA_HUMANO, reason=payload.reason)
    return resp.model_dump(), CallFinalState.TRANSFERIDA_HUMANO


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "authenticate_member": _handle_authenticate_member,
    "get_authorization_status": _handle_get_authorization_status,
    "search_providers": _handle_search_providers,
    "handoff_human": _handle_handoff_human,
}


def _parse_arguments(arguments_raw: object) -> dict:
    if isinstance(arguments_raw, str):
        try:
            arguments_raw = json.loads(arguments_raw)
        except json.JSONDecodeError:
            raise ValueError("arguments deve ser objeto JSON")
    if not isinstance(arguments_raw, dict):
        raise ValueError("arguments deve ser objeto")
    if len(arguments_raw) == 0:
        raise ValueError("arguments vazio")
    return arguments_raw


def _is_authorized(http_request: Request, settings: Settings) -> bool:
    """
    Validate optional webhook secret. If no secret is configured, accept request.
    """
    if not settings.webhook_secret:
        return True
    received_secret = http_request.headers.get(settings.webhook_secret_header)
    if not received_secret:
        return False
    return hmac.compare_digest(received_secret, settings.webhook_secret)


def _wrap_result(tool_call_id: str | None, result: ToolResponse) -> dict:
    return {"results": [{"toolCallId": tool_call_id, "result": result.model_dump()}]}


@router.post("/tools")
async def dispatch_tools(
    http_request: Request,
    payload: dict = Body(...),
    settings: Settings = Depends(get_settings),
):
    """
    Entry point for Vapi tool-calls (message.type='tool-calls') returning always HTTP 200 with results array.
    """
    tool_name = "unknown"
    call_id = str(uuid.uuid4())
    to_number = None
    tool_call_id = None
    arguments: dict | None = None
    tenant_id: str | None = None
    started_at = time.perf_counter()

    def finalize(
        payload_dict: dict,
        *,
        ok: bool,
        final_state: CallFinalState,
        event_type: str,
        error_code: str | None = None,
    ) -> dict:
        duration_ms = (time.perf_counter() - started_at) * 1000
        metrics_store.record(tool_name=tool_name, ok=ok, final_state=final_state, duration_ms=duration_ms)
        record_call_event(
            settings=settings,
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            event_type=event_type,
            final_state=final_state.value,
            ok=ok,
            duration_ms=duration_ms,
            error_code=error_code,
            payload=payload_dict,
        )
        return payload_dict

    # Accept both wrapped (message.toolCallList) and flat (toolCallList) envelopes
    message = payload.get("message") if isinstance(payload, dict) else None
    container = message if isinstance(message, dict) else payload

    if isinstance(container, dict):
        call = container.get("call", {})
        if isinstance(call, dict):
            call_id = call.get("id") or call_id
            to_number = call.get("to")

        tool_list = container.get("toolCallList")
        if tool_list and isinstance(tool_list, list) and len(tool_list) > 0:
            first = tool_list[0] or {}
            tool_call_id = first.get("id")
            tool_name = first.get("name") or "unknown"
            if "function" in first and isinstance(first.get("function"), dict):
                # backward compatibility
                tool_name = first["function"].get("name") or tool_name
                arguments_raw = first["function"].get("arguments")
            else:
                arguments_raw = first.get("arguments")
            try:
                arguments = _parse_arguments(arguments_raw)
            except ValueError as exc:
                arguments = None
                error = ToolError(code="VALIDATION", message=str(exc))
                log.warning(
                    "tool_argument_validation",
                    event_type="validation_error",
                    tenant_id=resolve_tenant(to_number, settings),
                    call_id=call_id,
                    tool_name=tool_name,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    message=str(exc),
                )
                response = ToolResponse(
                    ok=False,
                    tool_name=tool_name,
                    error=error,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                )
                return finalize(
                    _wrap_result(tool_call_id, response),
                    ok=response.ok,
                    final_state=response.final_state,
                    event_type="tool_argument_validation",
                    error_code=error.code,
                )

    tenant_id = resolve_tenant(to_number, settings)
    set_call_context(call_id, tenant_id)

    if not _is_authorized(http_request, settings):
        log.warning(
            "webhook_unauthorized",
            event_type="security",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
        )
        clear_call_context()
        return finalize(
            {"results": []},
            ok=False,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
            event_type="webhook_unauthorized",
            error_code="UNAUTHORIZED",
        )

    # Ignore if no tool call data
    if tool_call_id is None or tool_name == "unknown" or arguments is None:
        log.info(
            "event_ignored",
            event_type="event_ignored",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
        )
        clear_call_context()
        return finalize(
            {"results": []},
            ok=False,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
            event_type="event_ignored",
            error_code="IGNORED",
        )

    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        log.warning(
            "tool_not_found",
            event_type="validation_error",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
        )
        clear_call_context()
        error = ToolError(code="VALIDATION", message="tool_name invalido")
        response = ToolResponse(
            ok=False,
            tool_name=tool_name,
            error=error,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
        )
        return finalize(
            _wrap_result(tool_call_id, response),
            ok=response.ok,
            final_state=response.final_state,
            event_type="tool_not_found",
            error_code=error.code,
        )

    try:
        data, final_state = await handler(arguments, settings, call_id, tenant_id)
        response = ToolResponse(
            ok=True,
            tool_name=tool_name,
            data=data,
            final_state=final_state,
        )
    except ValidationError as exc:
        log.warning(
            "tool_argument_validation",
            event_type="validation_error",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
            message=str(exc),
        )
        response = ToolResponse(
            ok=False,
            error=ToolError(code="VALIDATION", message="argumentos invalidos"),
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
        )
    except TimeoutError as exc:
        log.error(
            "tool_timeout",
            event_type="error",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
            message=str(exc),
        )
        response = ToolResponse(
            ok=False,
            error=ToolError(code="TIMEOUT", message=str(exc)),
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
        )
    except ValueError as exc:
        log.warning(
            "tool_validation",
            event_type="validation_error",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
            message=str(exc),
        )
        response = ToolResponse(
            ok=False,
            error=ToolError(code="VALIDATION", message=str(exc)),
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
        )
    except RuntimeError as exc:
        log.error(
            "tool_upstream_503",
            event_type="error",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
            message=str(exc),
        )
        response = ToolResponse(
            ok=False,
            error=ToolError(code="UPSTREAM_503", message=str(exc)),
            tool_name=tool_name,
            final_state=CallFinalState.TRANSFERIDA_HUMANO,
        )
    finally:
        clear_call_context()

    log.info(
        "tool_completed",
        event_type="tool_completed",
        tenant_id=tenant_id,
        call_id=call_id,
        tool_name=tool_name,
        final_state=response.final_state,
        ok=response.ok,
        tool_call_id=tool_call_id,
    )
    error_code = response.error.code if response.error else None
    return finalize(
        _wrap_result(tool_call_id, response),
        ok=response.ok,
        final_state=response.final_state,
        event_type="tool_completed",
        error_code=error_code,
    )
