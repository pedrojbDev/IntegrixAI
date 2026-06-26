from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.tools.exceptions import BusinessRuleError
from app.core.tools.registry import TenantToolRegistry
from app.db import Base
from app.schemas.tools import ToolError
from app.services.tool_dispatcher import ToolDispatcher
from app.utils.enums import CallFinalState


class ToolDispatcherTests(unittest.IsolatedAsyncioTestCase):
    def _session_local(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        return sessionmaker(bind=engine, autocommit=False, autoflush=False)

    async def test_dispatch_keeps_response_envelope_for_success(self) -> None:
        settings = Settings(
            _env_file=None,
            default_tenant="tenant_default",
            tenant_map={"+5511999999999": "tenant_a"},
        )
        handler = AsyncMock(return_value=({"status": "queued"}, CallFinalState.TRANSFERIDA_HUMANO))
        registry = TenantToolRegistry()
        registry.register("pbsaude", "handoff_human", handler)
        dispatcher = ToolDispatcher(settings, registry=registry)
        request = SimpleNamespace(headers={})
        payload = {
            "message": {
                "call": {"id": "call_123", "to": "+5511999999999"},
                "toolCallList": [
                    {
                        "id": "tc_001",
                        "name": "handoff_human",
                        "arguments": {"reason": "fallback"},
                    }
                ],
            }
        }

        with (
            patch("app.core.tools.dispatcher.metrics_store.record"),
            patch("app.core.tools.dispatcher.record_call_event"),
            patch("app.core.tools.dispatcher.set_call_context"),
            patch("app.core.tools.dispatcher.clear_call_context"),
        ):
            result = await dispatcher.dispatch(request, payload)

        handler.assert_awaited_once_with({"reason": "fallback"}, settings, "call_123", "tenant_a")
        self.assertEqual(
            {
                "results": [
                    {
                        "toolCallId": "tc_001",
                        "result": {
                            "ok": True,
                            "tool_name": "handoff_human",
                            "data": {"status": "queued"},
                            "error": None,
                            "final_state": CallFinalState.TRANSFERIDA_HUMANO,
                        },
                    }
                ]
            },
            result,
        )

    async def test_dispatch_records_tenant_on_argument_validation(self) -> None:
        settings = Settings(
            _env_file=None,
            default_tenant="tenant_default",
            tenant_map={"+5511999999999": "tenant_a"},
        )
        dispatcher = ToolDispatcher(settings)
        request = SimpleNamespace(headers={})
        payload = {
            "message": {
                "call": {"id": "call_123", "to": "+5511999999999"},
                "toolCallList": [
                    {
                        "id": "tc_001",
                        "name": "handoff_human",
                        "arguments": "not-json",
                    }
                ],
            }
        }

        with (
            patch("app.core.tools.dispatcher.metrics_store.record"),
            patch("app.core.tools.dispatcher.set_call_context"),
            patch("app.core.tools.dispatcher.clear_call_context"),
            patch("app.core.tools.dispatcher.record_call_event") as record_call_event,
        ):
            result = await dispatcher.dispatch(request, payload)

        self.assertEqual("tenant_a", record_call_event.call_args.kwargs["tenant_id"])
        self.assertEqual(
            ToolError(code="VALIDATION", message="arguments deve ser objeto JSON").model_dump(),
            result["results"][0]["result"]["error"],
        )

    async def test_dispatch_resolves_tenant_from_assistant_id_when_to_number_is_missing(self) -> None:
        settings = Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://app:secret@db.prod.internal:5432/integrix",
            db_enabled=True,
            data_mode="external_api",
            tenant_map={},
            tenant_assistant_map={"assistant_123": "tenant_a"},
            webhook_secret="secret",
            ops_dashboard_token="ops-token",
            audit_write_mode="async",
            external_api_base_url="https://api.customer-prod.internal",
            external_api_auth_type="basic",
            external_api_username="user",
            external_api_password="password",
        )
        handler = AsyncMock(return_value=({"status": "queued"}, CallFinalState.TRANSFERIDA_HUMANO))
        registry = TenantToolRegistry()
        registry.register("pbsaude", "handoff_human", handler)
        dispatcher = ToolDispatcher(settings, registry=registry)
        request = SimpleNamespace(headers={"x-webhook-secret": "secret"})
        payload = {
            "message": {
                "call": {"id": "call_123", "to": None, "assistantId": "assistant_123"},
                "toolCallList": [
                    {
                        "id": "tc_001",
                        "name": "handoff_human",
                        "arguments": {"reason": "fallback"},
                    }
                ],
            }
        }

        with (
            patch("app.core.tools.dispatcher.metrics_store.record"),
            patch("app.core.tools.dispatcher.record_call_event"),
            patch("app.core.tools.dispatcher.set_call_context"),
            patch("app.core.tools.dispatcher.clear_call_context"),
        ):
            result = await dispatcher.dispatch(request, payload)

        handler.assert_awaited_once_with({"reason": "fallback"}, settings, "call_123", "tenant_a")
        self.assertTrue(result["results"][0]["result"]["ok"])

    async def test_dispatch_returns_cached_result_for_duplicate_tool_call(self) -> None:
        session_local = self._session_local()
        settings = Settings(
            _env_file=None,
            db_enabled=True,
            default_tenant="tenant_default",
            tenant_map={"+5511999999999": "tenant_a"},
        )
        handler = AsyncMock(return_value=({"status": "queued"}, CallFinalState.TRANSFERIDA_HUMANO))
        registry = TenantToolRegistry()
        registry.register("pbsaude", "handoff_human", handler)
        dispatcher = ToolDispatcher(settings, registry=registry)
        request = SimpleNamespace(headers={})
        payload = {
            "message": {
                "call": {"id": "call_123", "to": "+5511999999999"},
                "toolCallList": [
                    {
                        "id": "tc_001",
                        "name": "handoff_human",
                        "arguments": {"reason": "fallback"},
                    }
                ],
            }
        }

        with (
            patch("app.core.tools.idempotency.SessionLocal", session_local),
            patch("app.core.tools.dispatcher.record_call_event"),
            patch("app.core.tools.dispatcher.metrics_store.record"),
        ):
            first = await dispatcher.dispatch(request, payload)
            second = await dispatcher.dispatch(request, payload)

        handler.assert_awaited_once()
        self.assertEqual(first, second)

    async def test_dispatch_records_idempotency_hit_event_for_duplicate_tool_call(self) -> None:
        session_local = self._session_local()
        settings = Settings(
            _env_file=None,
            db_enabled=True,
            default_tenant="tenant_default",
            tenant_map={"+5511999999999": "tenant_a"},
        )
        handler = AsyncMock(return_value=({"status": "queued"}, CallFinalState.TRANSFERIDA_HUMANO))
        registry = TenantToolRegistry()
        registry.register("pbsaude", "handoff_human", handler)
        dispatcher = ToolDispatcher(settings, registry=registry)
        request = SimpleNamespace(headers={})
        payload = {
            "message": {
                "call": {"id": "call_123", "to": "+5511999999999"},
                "toolCallList": [
                    {
                        "id": "tc_001",
                        "name": "handoff_human",
                        "arguments": {"reason": "fallback"},
                    }
                ],
            }
        }

        with (
            patch("app.core.tools.idempotency.SessionLocal", session_local),
            patch("app.core.tools.dispatcher.metrics_store.record"),
            patch("app.core.tools.dispatcher.record_call_event") as record_call_event,
        ):
            await dispatcher.dispatch(request, payload)
            await dispatcher.dispatch(request, payload)

        recorded_events = [call.kwargs["event_type"] for call in record_call_event.call_args_list]
        self.assertIn("idempotency_hit", recorded_events)

    async def test_idempotency_is_scoped_by_tenant(self) -> None:
        session_local = self._session_local()
        settings = Settings(
            _env_file=None,
            db_enabled=True,
            tenant_map={
                "+5511999999999": "tenant_a",
                "+5511888888888": "tenant_b",
            },
        )
        handler = AsyncMock(
            side_effect=[
                ({"status": "tenant_a"}, CallFinalState.TRANSFERIDA_HUMANO),
                ({"status": "tenant_b"}, CallFinalState.TRANSFERIDA_HUMANO),
            ]
        )
        registry = TenantToolRegistry()
        registry.register("pbsaude", "handoff_human", handler)
        dispatcher = ToolDispatcher(settings, registry=registry)
        request = SimpleNamespace(headers={})

        def payload(to_number: str):
            return {
                "message": {
                    "call": {"id": "call_123", "to": to_number},
                    "toolCallList": [
                        {
                            "id": "tc_001",
                            "name": "handoff_human",
                            "arguments": {"reason": "fallback"},
                        }
                    ],
                }
            }

        with (
            patch("app.core.tools.idempotency.SessionLocal", session_local),
            patch("app.core.tools.dispatcher.record_call_event"),
            patch("app.core.tools.dispatcher.metrics_store.record"),
        ):
            first = await dispatcher.dispatch(request, payload("+5511999999999"))
            second = await dispatcher.dispatch(request, payload("+5511888888888"))

        self.assertEqual(2, handler.await_count)
        self.assertEqual("tenant_a", first["results"][0]["result"]["data"]["status"])
        self.assertEqual("tenant_b", second["results"][0]["result"]["data"]["status"])

    async def test_dispatch_processes_multiple_tool_calls(self) -> None:
        settings = Settings(
            _env_file=None,
            tenant_map={"+5511999999999": "tenant_a"},
        )
        handoff = AsyncMock(return_value=({"status": "queued"}, CallFinalState.TRANSFERIDA_HUMANO))
        search = AsyncMock(
            return_value=({"providers": []}, CallFinalState.RESOLVIDA_AUTOMATICO)
        )
        registry = TenantToolRegistry()
        registry.register("pbsaude", "handoff_human", handoff)
        registry.register("pbsaude", "search_providers", search)
        dispatcher = ToolDispatcher(settings, registry=registry)
        request = SimpleNamespace(headers={})
        payload = {
            "message": {
                "call": {"id": "call_123", "to": "+5511999999999"},
                "toolCallList": [
                    {
                        "id": "tc_handoff",
                        "name": "handoff_human",
                        "arguments": {"reason": "fallback"},
                    },
                    {
                        "id": "tc_search",
                        "name": "search_providers",
                        "arguments": {
                            "cpf": "03457351538",
                            "cidade": "feira de santana",
                            "especialidade": "cardiologia",
                        },
                    },
                ],
            }
        }

        with (
            patch("app.core.tools.dispatcher.record_call_event"),
            patch("app.core.tools.dispatcher.metrics_store.record"),
        ):
            result = await dispatcher.dispatch(request, payload)

        handoff.assert_awaited_once()
        search.assert_awaited_once()
        self.assertEqual(["tc_handoff", "tc_search"], [item["toolCallId"] for item in result["results"]])

    async def test_business_error_retries_once_then_handoffs(self) -> None:
        session_local = self._session_local()
        settings = Settings(
            _env_file=None,
            db_enabled=True,
            tenant_map={"+5511999999999": "tenant_a"},
        )
        handler = AsyncMock(
            side_effect=BusinessRuleError(
                code="CPF_INVALIDO",
                field="cpf",
                message="CPF deve conter 11 digitos",
            )
        )
        registry = TenantToolRegistry()
        registry.register("pbsaude", "search_providers", handler)
        dispatcher = ToolDispatcher(settings, registry=registry)
        request = SimpleNamespace(headers={})

        def payload(tool_call_id: str):
            return {
                "message": {
                    "call": {"id": "call_123", "to": "+5511999999999"},
                    "toolCallList": [
                        {
                            "id": tool_call_id,
                            "name": "search_providers",
                            "arguments": {"cpf": "123"},
                        }
                    ],
                }
            }

        with (
            patch("app.core.tools.idempotency.SessionLocal", session_local),
            patch("app.core.tools.dispatcher.record_call_event"),
            patch("app.core.tools.dispatcher.metrics_store.record"),
        ):
            first = await dispatcher.dispatch(request, payload("tc_001"))
            second = await dispatcher.dispatch(request, payload("tc_002"))

        first_result = first["results"][0]["result"]
        second_result = second["results"][0]["result"]
        self.assertEqual(CallFinalState.RESOLVIDA_AUTOMATICO, first_result["final_state"])
        self.assertTrue(first_result["data"]["retryable"])
        self.assertEqual(1, first_result["data"]["attempt"])
        self.assertEqual(CallFinalState.TRANSFERIDA_HUMANO, second_result["final_state"])
        self.assertFalse(second_result["data"]["retryable"])
        self.assertEqual(2, second_result["data"]["attempt"])


if __name__ == "__main__":
    unittest.main()
