from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Mapping

from fastapi import HTTPException, Request
from pydantic import ValidationError

from ...config import Settings
from ...logging import get_logger
from ...platform.services.tenant_config_service import TenantConfigService
from ...utils.enums import CallFinalState
from ..audit.service import record_call_event
from ..context import clear_call_context, set_call_context
from ..metrics.service import metrics_store
from ..security.webhook import is_webhook_authorized
from ..tenant.models import TenantResolution
from ..tenant.resolver import resolve_tenant_details, should_reject_tenant_resolution
from .contracts import ToolError, ToolResponse
from .exceptions import BusinessRuleError
from .registry import TenantToolRegistry, ToolHandler, tool_registry


@dataclass(slots=True)
class ParsedToolInvocation:
    call_id: str
    to_number: str | None
    tool_call_id: str | None
    tool_name: str
    arguments: dict | None
    arguments_error: str | None = None


class ToolDispatcher:
    """Dispatch tool calls through tenant-aware implementation registry."""

    def __init__(
        self,
        settings: Settings,
        registry: TenantToolRegistry | Mapping[str, ToolHandler] | None = None,
        tenant_config_service: TenantConfigService | None = None,
    ):
        self.settings = settings
        self.registry = self._coerce_registry(registry)
        self.tenant_config_service = tenant_config_service or TenantConfigService(settings)
        self.log = get_logger()

    async def dispatch(self, http_request: Request, payload: dict) -> dict:
        parsed = self._parse_invocation(payload)
        resolution = resolve_tenant_details(parsed.to_number, self.settings)
        tenant_rejected = should_reject_tenant_resolution(resolution, self.settings)
        tenant_id = "unknown" if tenant_rejected else resolution.tenant_id
        implementation_key = (
            "unresolved"
            if tenant_rejected
            else self.tenant_config_service.get_implementation_key(tenant_id)
        )
        started_at = time.perf_counter()

        if resolution.used_fallback:
            self._log_tenant_fallback(parsed.call_id, parsed.tool_name, resolution, tenant_id=tenant_id)

        def finalize(
            payload_dict: dict,
            *,
            ok: bool,
            final_state: CallFinalState,
            event_type: str,
            error_code: str | None = None,
        ) -> dict:
            duration_ms = (time.perf_counter() - started_at) * 1000
            metrics_store.record(
                tool_name=parsed.tool_name,
                ok=ok,
                final_state=final_state,
                duration_ms=duration_ms,
            )
            record_call_event(
                settings=self.settings,
                tenant_id=tenant_id,
                call_id=parsed.call_id,
                tool_name=parsed.tool_name,
                event_type=event_type,
                final_state=final_state.value,
                ok=ok,
                duration_ms=duration_ms,
                error_code=error_code,
                payload=payload_dict,
            )
            return payload_dict

        if parsed.arguments_error is not None:
            error = ToolError(code="VALIDATION", message=parsed.arguments_error)
            self.log.warning(
                "tool_argument_validation",
                event_type="validation_error",
                tenant_id=tenant_id,
                call_id=parsed.call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                message=parsed.arguments_error,
                implementation_key=implementation_key,
            )
            response = ToolResponse(
                ok=False,
                tool_name=parsed.tool_name,
                error=error,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
            )
            return finalize(
                self._wrap_result(parsed.tool_call_id, response),
                ok=response.ok,
                final_state=response.final_state,
                event_type="tool_argument_validation",
                error_code=error.code,
            )

        set_call_context(parsed.call_id, tenant_id)
        try:
            if not is_webhook_authorized(http_request, self.settings):
                self.log.warning(
                    "webhook_unauthorized",
                    event_type="security",
                    tenant_id=tenant_id,
                    call_id=parsed.call_id,
                    tool_name=parsed.tool_name,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    implementation_key=implementation_key,
                )
                return finalize(
                    {"results": []},
                    ok=False,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    event_type="webhook_unauthorized",
                    error_code="UNAUTHORIZED",
                )

            if tenant_rejected:
                self.log.warning(
                    "tenant_resolution_rejected",
                    event_type="tenant_resolution_rejected",
                    tenant_id=tenant_id,
                    call_id=parsed.call_id,
                    tool_name=parsed.tool_name,
                    to_number=resolution.to_number,
                    resolution_source=resolution.source,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    implementation_key=implementation_key,
                )
                error = ToolError(code="VALIDATION", message="tenant nao resolvido")
                response = ToolResponse(
                    ok=False,
                    tool_name=parsed.tool_name,
                    error=error,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                )
                return finalize(
                    self._wrap_result(parsed.tool_call_id, response)
                    if parsed.tool_call_id
                    else {"results": []},
                    ok=response.ok,
                    final_state=response.final_state,
                    event_type="tenant_resolution_rejected",
                    error_code=error.code,
                )

            if parsed.tool_call_id is None or parsed.tool_name == "unknown" or parsed.arguments is None:
                self.log.info(
                    "event_ignored",
                    event_type="event_ignored",
                    tenant_id=tenant_id,
                    call_id=parsed.call_id,
                    tool_name=parsed.tool_name,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    implementation_key=implementation_key,
                )
                return finalize(
                    {"results": []},
                    ok=False,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    event_type="event_ignored",
                    error_code="IGNORED",
                )

            handler = self.registry.get_handler(implementation_key, parsed.tool_name)
            if handler is None:
                self.log.warning(
                    "tool_not_found",
                    event_type="validation_error",
                    tenant_id=tenant_id,
                    call_id=parsed.call_id,
                    tool_name=parsed.tool_name,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    implementation_key=implementation_key,
                )
                error = ToolError(code="VALIDATION", message="tool_name invalido")
                response = ToolResponse(
                    ok=False,
                    tool_name=parsed.tool_name,
                    error=error,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                )
                return finalize(
                    self._wrap_result(parsed.tool_call_id, response),
                    ok=response.ok,
                    final_state=response.final_state,
                    event_type="tool_not_found",
                    error_code=error.code,
                )

            response = await self._run_handler(
                handler,
                parsed=parsed,
                tenant_id=tenant_id,
                implementation_key=implementation_key,
            )
        finally:
            clear_call_context()

        self.log.info(
            "tool_completed",
            event_type="tool_completed",
            tenant_id=tenant_id,
            call_id=parsed.call_id,
            tool_name=parsed.tool_name,
            final_state=response.final_state,
            ok=response.ok,
            tool_call_id=parsed.tool_call_id,
            implementation_key=implementation_key,
        )
        error_code = response.error.code if response.error else None
        return finalize(
            self._wrap_result(parsed.tool_call_id, response),
            ok=response.ok,
            final_state=response.final_state,
            event_type="tool_completed",
            error_code=error_code,
        )

    async def _run_handler(
        self,
        handler,
        *,
        parsed: ParsedToolInvocation,
        tenant_id: str,
        implementation_key: str,
    ) -> ToolResponse:
        try:
            data, final_state = await handler(
                parsed.arguments or {},
                self.settings,
                parsed.call_id,
                tenant_id,
            )
            return ToolResponse(
                ok=True,
                tool_name=parsed.tool_name,
                data=data,
                final_state=final_state,
            )
        except ValidationError as exc:
            self.log.warning(
                "tool_argument_validation",
                event_type="validation_error",
                tenant_id=tenant_id,
                call_id=parsed.call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                message=str(exc),
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code="VALIDATION", message="argumentos invalidos"),
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
            )
        except BusinessRuleError as exc:
            self.log.warning(
                "tool_business_validation",
                event_type="business_error",
                tenant_id=tenant_id,
                call_id=parsed.call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.RESOLVIDA_AUTOMATICO,
                upstream_code=exc.code,
                field=exc.field,
                message=exc.message,
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code="VALIDATION", message=exc.message),
                data={
                    "retryable": True,
                    "field": exc.field,
                    "upstream_code": exc.code,
                    **(exc.details or {}),
                },
                tool_name=parsed.tool_name,
                final_state=CallFinalState.RESOLVIDA_AUTOMATICO,
            )
        except TimeoutError as exc:
            self.log.error(
                "tool_timeout",
                event_type="error",
                tenant_id=tenant_id,
                call_id=parsed.call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                message=str(exc),
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code="TIMEOUT", message=str(exc)),
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
            )
        except HTTPException as exc:
            error_code = "UPSTREAM_503" if exc.status_code >= 500 else "VALIDATION"
            self.log.error(
                "tool_http_exception",
                event_type="error",
                tenant_id=tenant_id,
                call_id=parsed.call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                status_code=exc.status_code,
                message=str(exc.detail),
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code=error_code, message=str(exc.detail)),
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
            )
        except ValueError as exc:
            self.log.warning(
                "tool_validation",
                event_type="validation_error",
                tenant_id=tenant_id,
                call_id=parsed.call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                message=str(exc),
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code="VALIDATION", message=str(exc)),
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
            )
        except RuntimeError as exc:
            self.log.error(
                "tool_upstream_503",
                event_type="error",
                tenant_id=tenant_id,
                call_id=parsed.call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                message=str(exc),
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code="UPSTREAM_503", message=str(exc)),
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
            )

    def _log_tenant_fallback(
        self,
        call_id: str,
        tool_name: str,
        resolution: TenantResolution,
        *,
        tenant_id: str | None = None,
    ) -> None:
        log_method = self.log.warning if resolution.source == "default_tenant" else self.log.info
        log_method(
            "tenant_resolution_fallback",
            event_type="tenant_resolution",
            tenant_id=tenant_id or resolution.tenant_id,
            call_id=call_id,
            tool_name=tool_name,
            to_number=resolution.to_number,
            resolution_source=resolution.source,
        )

    def _parse_invocation(self, payload: dict) -> ParsedToolInvocation:
        call_id = str(uuid.uuid4())
        to_number = None
        tool_call_id = None
        tool_name = "unknown"
        arguments: dict | None = None
        arguments_error: str | None = None

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
                    tool_name = first["function"].get("name") or tool_name
                    arguments_raw = first["function"].get("arguments")
                else:
                    arguments_raw = first.get("arguments")
                try:
                    arguments = self._parse_arguments(arguments_raw)
                except ValueError as exc:
                    arguments_error = str(exc)

        return ParsedToolInvocation(
            call_id=call_id,
            to_number=to_number,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            arguments_error=arguments_error,
        )

    @staticmethod
    def _parse_arguments(arguments_raw: object) -> dict:
        if isinstance(arguments_raw, str):
            try:
                arguments_raw = json.loads(arguments_raw)
            except json.JSONDecodeError as exc:
                raise ValueError("arguments deve ser objeto JSON") from exc
        if not isinstance(arguments_raw, dict):
            raise ValueError("arguments deve ser objeto")
        if len(arguments_raw) == 0:
            raise ValueError("arguments vazio")
        return arguments_raw

    @staticmethod
    def _wrap_result(tool_call_id: str | None, result: ToolResponse) -> dict:
        return {"results": [{"toolCallId": tool_call_id, "result": result.model_dump()}]}

    def _coerce_registry(
        self,
        registry: TenantToolRegistry | Mapping[str, ToolHandler] | None,
    ) -> TenantToolRegistry:
        if registry is None:
            return tool_registry
        if isinstance(registry, TenantToolRegistry):
            return registry

        compatibility_registry = TenantToolRegistry()
        for tool_name, handler in registry.items():
            compatibility_registry.register(
                self.settings.default_tenant_implementation,
                tool_name,
                handler,
            )
        return compatibility_registry
