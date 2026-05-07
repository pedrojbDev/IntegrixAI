from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.core.tools.registry import TenantToolRegistry
from app.schemas.tools import ToolError
from app.services.tool_dispatcher import ToolDispatcher
from app.utils.enums import CallFinalState


class ToolDispatcherTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
