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
from .idempotency import (
    get_cached_tool_result,
    record_business_error_attempt,
    save_tool_result,
)
from .registry import TenantToolRegistry, ToolHandler, tool_registry

BUSINESS_ERROR_MAX_ATTEMPTS = 2


@dataclass(slots=True)
class ParsedToolInvocation:
    tool_call_id: str | None
    tool_name: str
    arguments: dict | None
    arguments_error: str | None = None


@dataclass(slots=True)
class ParsedToolRequest:
    call_id: str
    to_number: str | None
    assistant_id: str | None
    phone_number_id: str | None
    invocations: list[ParsedToolInvocation]


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
        parsed_request = self._parse_request(payload)
        first_tool_name = (
            parsed_request.invocations[0].tool_name if parsed_request.invocations else "unknown"
        )
        resolution = resolve_tenant_details(
            parsed_request.to_number,
            self.settings,
            assistant_id=parsed_request.assistant_id,
            phone_number_id=parsed_request.phone_number_id,
        )
        tenant_rejected = should_reject_tenant_resolution(resolution, self.settings)
        tenant_id = "unknown" if tenant_rejected else resolution.tenant_id
        implementation_key = (
            "unresolved"
            if tenant_rejected
            else self.tenant_config_service.get_implementation_key(tenant_id)
        )

        if resolution.used_fallback:
            self._log_tenant_fallback(
                parsed_request.call_id,
                first_tool_name,
                resolution,
                tenant_id=tenant_id,
            )

        set_call_context(parsed_request.call_id, tenant_id)
        try:
            if not is_webhook_authorized(http_request, self.settings):
                self.log.warning(
                    "webhook_unauthorized",
                    event_type="security",
                    tenant_id=tenant_id,
                    call_id=parsed_request.call_id,
                    tool_name=first_tool_name,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    implementation_key=implementation_key,
                )
                return self._record_request_event(
                    {"results": []},
                    tenant_id=tenant_id,
                    call_id=parsed_request.call_id,
                    tool_name=first_tool_name,
                    ok=False,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    event_type="webhook_unauthorized",
                    error_code="UNAUTHORIZED",
                )

            if tenant_rejected:
                results = []
                for parsed in parsed_request.invocations:
                    results.append(
                        self._tenant_rejected_result(
                            parsed,
                            tenant_id=tenant_id,
                            call_id=parsed_request.call_id,
                            resolution=resolution,
                            implementation_key=implementation_key,
                        )
                    )
                return {"results": results}

            if not parsed_request.invocations:
                self.log.info(
                    "event_ignored",
                    event_type="event_ignored",
                    tenant_id=tenant_id,
                    call_id=parsed_request.call_id,
                    tool_name=first_tool_name,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    implementation_key=implementation_key,
                )
                return self._record_request_event(
                    {"results": []},
                    tenant_id=tenant_id,
                    call_id=parsed_request.call_id,
                    tool_name=first_tool_name,
                    ok=False,
                    final_state=CallFinalState.TRANSFERIDA_HUMANO,
                    event_type="event_ignored",
                    error_code="IGNORED",
                )

            results = []
            for parsed in parsed_request.invocations:
                results.append(
                    await self._dispatch_one(
                        parsed,
                        call_id=parsed_request.call_id,
                        tenant_id=tenant_id,
                        implementation_key=implementation_key,
                    )
                )
            return {"results": results}
        finally:
            clear_call_context()

    async def _dispatch_one(
        self,
        parsed: ParsedToolInvocation,
        *,
        call_id: str,
        tenant_id: str,
        implementation_key: str,
    ) -> dict:
        cached = get_cached_tool_result(
            settings=self.settings,
            tenant_id=tenant_id,
            call_id=call_id,
            tool_call_id=parsed.tool_call_id,
        )
        if cached is not None:
            self.log.info(
                "tool_idempotency_hit",
                event_type="idempotency_hit",
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
                tool_name=parsed.tool_name,
                implementation_key=implementation_key,
            )
            metrics_store.record(
                tool_name=parsed.tool_name,
                ok=bool(cached.get("ok")),
                final_state=CallFinalState(cached["final_state"]),
                duration_ms=0.0,
            )
            record_call_event(
                settings=self.settings,
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
                tool_name=parsed.tool_name,
                event_type="idempotency_hit",
                final_state=str(cached.get("final_state")),
                ok=bool(cached.get("ok")),
                duration_ms=0.0,
                error_code=(cached.get("error") or {}).get("code") if isinstance(cached.get("error"), dict) else None,
                payload={"toolCallId": parsed.tool_call_id, "result": cached},
            )
            return {"toolCallId": parsed.tool_call_id, "result": cached}

        started_at = time.perf_counter()

        if parsed.arguments_error is not None:
            error = ToolError(code="VALIDATION", message=parsed.arguments_error)
            self.log.warning(
                "tool_argument_validation",
                event_type="validation_error",
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
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
            return self._finalize_invocation(
                parsed,
                response,
                call_id=call_id,
                tenant_id=tenant_id,
                started_at=started_at,
                event_type="tool_argument_validation",
                error_code=error.code,
            )

        if parsed.tool_call_id is None or parsed.tool_name == "unknown" or parsed.arguments is None:
            self.log.info(
                "event_ignored",
                event_type="event_ignored",
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                implementation_key=implementation_key,
            )
            response = ToolResponse(
                ok=False,
                tool_name=parsed.tool_name,
                error=ToolError(code="VALIDATION", message="tool call invalido"),
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
            )
            return self._finalize_invocation(
                parsed,
                response,
                call_id=call_id,
                tenant_id=tenant_id,
                started_at=started_at,
                event_type="event_ignored",
                error_code="IGNORED",
            )

        handler = self.registry.get_handler(implementation_key, parsed.tool_name)
        if handler is None:
            self.log.warning(
                "tool_not_found",
                event_type="validation_error",
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
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
            return self._finalize_invocation(
                parsed,
                response,
                call_id=call_id,
                tenant_id=tenant_id,
                started_at=started_at,
                event_type="tool_not_found",
                error_code=error.code,
            )

        response = await self._run_handler(
            handler,
            parsed=parsed,
            call_id=call_id,
            tenant_id=tenant_id,
            implementation_key=implementation_key,
        )
        self.log.info(
            "tool_completed",
            event_type="tool_completed",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_name=parsed.tool_name,
            final_state=response.final_state,
            ok=response.ok,
            tool_call_id=parsed.tool_call_id,
            implementation_key=implementation_key,
        )
        error_code = response.error.code if response.error else None
        return self._finalize_invocation(
            parsed,
            response,
            call_id=call_id,
            tenant_id=tenant_id,
            started_at=started_at,
            event_type="tool_completed",
            error_code=error_code,
        )

    def _tenant_rejected_result(
        self,
        parsed: ParsedToolInvocation,
        *,
        tenant_id: str,
        call_id: str,
        resolution: TenantResolution,
        implementation_key: str,
    ) -> dict:
        self.log.warning(
            "tenant_resolution_rejected",
            event_type="tenant_resolution_rejected",
            tenant_id=tenant_id,
            call_id=call_id,
            tool_call_id=parsed.tool_call_id,
            tool_name=parsed.tool_name,
            to_number=resolution.to_number,
            tenant_identifier=resolution.identifier,
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
        return self._finalize_invocation(
            parsed,
            response,
            call_id=call_id,
            tenant_id=tenant_id,
            started_at=time.perf_counter(),
            event_type="tenant_resolution_rejected",
            error_code=error.code,
            save_idempotency=False,
        )

    async def _run_handler(
        self,
        handler,
        *,
        parsed: ParsedToolInvocation,
        call_id: str,
        tenant_id: str,
        implementation_key: str,
    ) -> ToolResponse:
        try:
            data, final_state = await handler(
                parsed.arguments or {},
                self.settings,
                call_id,
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
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
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
            attempt = record_business_error_attempt(
                settings=self.settings,
                tenant_id=tenant_id,
                call_id=call_id,
                tool_name=parsed.tool_name,
                field=exc.field,
                upstream_code=exc.code,
            )
            retryable = exc.retryable and (
                not exc.handoff_after_retry or attempt < BUSINESS_ERROR_MAX_ATTEMPTS
            )
            final_state = (
                CallFinalState.RESOLVIDA_AUTOMATICO
                if retryable
                else CallFinalState.TRANSFERIDA_HUMANO
            )
            self.log.warning(
                "tool_business_validation",
                event_type="business_error",
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
                tool_name=parsed.tool_name,
                final_state=final_state,
                upstream_code=exc.code,
                field=exc.field,
                retryable=retryable,
                attempt=attempt,
                max_attempts=BUSINESS_ERROR_MAX_ATTEMPTS,
                message=exc.message,
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code="VALIDATION", message=exc.message),
                data={
                    "retryable": retryable,
                    "field": exc.field,
                    "upstream_code": exc.code,
                    "attempt": attempt,
                    "max_attempts": BUSINESS_ERROR_MAX_ATTEMPTS,
                    **(exc.details or {}),
                },
                tool_name=parsed.tool_name,
                final_state=final_state,
            )
        except TimeoutError as exc:
            self.log.error(
                "tool_timeout",
                event_type="error",
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                message=str(exc),
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code="TIMEOUT", message=str(exc)),
                data={"retryable": False},
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
            )
        except HTTPException as exc:
            error_code = "UPSTREAM_503" if exc.status_code >= 500 else "VALIDATION"
            self.log.error(
                "tool_http_exception",
                event_type="error",
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                status_code=exc.status_code,
                message=str(exc.detail),
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code=error_code, message=str(exc.detail)),
                data={"retryable": False},
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
            )
        except ValueError as exc:
            self.log.warning(
                "tool_validation",
                event_type="validation_error",
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
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
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
                tool_name=parsed.tool_name,
                final_state=CallFinalState.TRANSFERIDA_HUMANO,
                message=str(exc),
                implementation_key=implementation_key,
            )
            return ToolResponse(
                ok=False,
                error=ToolError(code="UPSTREAM_503", message=str(exc)),
                data={"retryable": False},
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
            tenant_identifier=resolution.identifier,
            resolution_source=resolution.source,
        )

    def _parse_request(self, payload: dict) -> ParsedToolRequest:
        call_id = str(uuid.uuid4())
        to_number = None
        assistant_id = None
        phone_number_id = None
        invocations: list[ParsedToolInvocation] = []

        message = payload.get("message") if isinstance(payload, dict) else None
        container = message if isinstance(message, dict) else payload

        if isinstance(container, dict):
            call = container.get("call", {})
            if isinstance(call, dict):
                call_id = call.get("id") or call_id
                to_number = call.get("to")
                assistant_id = self._first_string(
                    call.get("assistantId"),
                    call.get("assistant", {}).get("id") if isinstance(call.get("assistant"), dict) else None,
                    container.get("assistantId"),
                    container.get("assistant", {}).get("id") if isinstance(container.get("assistant"), dict) else None,
                )
                phone_number_id = self._first_string(
                    call.get("phoneNumberId"),
                    call.get("phoneNumber", {}).get("id")
                    if isinstance(call.get("phoneNumber"), dict)
                    else None,
                    container.get("phoneNumberId"),
                    container.get("phoneNumber", {}).get("id")
                    if isinstance(container.get("phoneNumber"), dict)
                    else None,
                )

            tool_list = container.get("toolCallList")
            if tool_list and isinstance(tool_list, list):
                for item in tool_list:
                    invocations.append(self._parse_tool_invocation(item))

        return ParsedToolRequest(
            call_id=call_id,
            to_number=to_number,
            assistant_id=assistant_id,
            phone_number_id=phone_number_id,
            invocations=invocations,
        )

    def _parse_tool_invocation(self, item: object) -> ParsedToolInvocation:
        if not isinstance(item, dict):
            return ParsedToolInvocation(
                tool_call_id=None,
                tool_name="unknown",
                arguments=None,
                arguments_error="tool call invalido",
            )

        tool_call_id = item.get("id")
        tool_name = item.get("name") or "unknown"
        if "function" in item and isinstance(item.get("function"), dict):
            tool_name = item["function"].get("name") or tool_name
            arguments_raw = item["function"].get("arguments")
        else:
            arguments_raw = item.get("arguments")

        arguments: dict | None = None
        arguments_error: str | None = None
        try:
            arguments = self._parse_arguments(arguments_raw)
        except ValueError as exc:
            arguments_error = str(exc)

        return ParsedToolInvocation(
            tool_call_id=str(tool_call_id) if tool_call_id is not None else None,
            tool_name=str(tool_name) if tool_name else "unknown",
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
    def _first_string(*values: object) -> str | None:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _wrap_result(tool_call_id: str | None, result: ToolResponse) -> dict:
        return {"results": [{"toolCallId": tool_call_id, "result": result.model_dump(mode="json")}]}

    def _finalize_invocation(
        self,
        parsed: ParsedToolInvocation,
        response: ToolResponse,
        *,
        call_id: str,
        tenant_id: str,
        started_at: float,
        event_type: str,
        error_code: str | None = None,
        save_idempotency: bool = True,
    ) -> dict:
        duration_ms = (time.perf_counter() - started_at) * 1000
        result_payload = response.model_dump(mode="json")
        wrapped = {"toolCallId": parsed.tool_call_id, "result": result_payload}
        metrics_store.record(
            tool_name=parsed.tool_name,
            ok=response.ok,
            final_state=response.final_state,
            duration_ms=duration_ms,
        )
        record_call_event(
            settings=self.settings,
            tenant_id=tenant_id,
            call_id=call_id,
            tool_call_id=parsed.tool_call_id,
            tool_name=parsed.tool_name,
            event_type=event_type,
            final_state=response.final_state.value,
            ok=response.ok,
            duration_ms=duration_ms,
            error_code=error_code,
            payload=wrapped,
        )
        if save_idempotency:
            save_tool_result(
                settings=self.settings,
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=parsed.tool_call_id,
                tool_name=parsed.tool_name,
                ok=response.ok,
                final_state=response.final_state,
                error_code=error_code,
                duration_ms=duration_ms,
                result_payload=result_payload,
            )
        return wrapped

    def _record_request_event(
        self,
        payload_dict: dict,
        *,
        tenant_id: str,
        call_id: str,
        tool_name: str,
        ok: bool,
        final_state: CallFinalState,
        event_type: str,
        error_code: str | None = None,
    ) -> dict:
        metrics_store.record(
            tool_name=tool_name,
            ok=ok,
            final_state=final_state,
            duration_ms=0.0,
        )
        record_call_event(
            settings=self.settings,
            tenant_id=tenant_id,
            call_id=call_id,
            tool_call_id=None,
            tool_name=tool_name,
            event_type=event_type,
            final_state=final_state.value,
            ok=ok,
            duration_ms=0.0,
            error_code=error_code,
            payload=payload_dict,
        )
        return payload_dict

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
