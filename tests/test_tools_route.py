import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.utils.enums import CallFinalState


def production_settings(**overrides):
    values = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql+psycopg://app:secret@db.example.com:5432/integrix",
        "db_enabled": True,
        "data_mode": "external_api",
        "tenant_map": {"+5511999999999": "tenant_a"},
        "webhook_secret": "secret",
        "ops_dashboard_token": "ops-token",
        "audit_write_mode": "async",
        "external_api_base_url": "https://customer-api.example",
        "external_api_auth_type": "basic",
        "external_api_username": "user",
        "external_api_password": "password",
    }
    values.update(overrides)
    return Settings(**values)


class ToolsRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_tools_route_keeps_success_envelope(self) -> None:
        settings = Settings(_env_file=None, tenant_map={"+5511999999999": "tenant_a"})
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.post(
            "/tools",
            json={
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
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "results": [
                    {
                        "toolCallId": "tc_001",
                        "result": {
                            "ok": True,
                            "tool_name": "handoff_human",
                            "data": {
                                "status": CallFinalState.TRANSFERIDA_HUMANO,
                                "reason": "fallback",
                            },
                            "error": None,
                            "final_state": CallFinalState.TRANSFERIDA_HUMANO,
                        },
                    }
                ]
            },
            response.json(),
        )

    def test_tools_route_argument_validation_keeps_same_envelope(self) -> None:
        settings = Settings(_env_file=None)
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.post(
            "/tools",
            json={
                "message": {
                    "call": {"id": "call_123"},
                    "toolCallList": [
                        {
                            "id": "tc_001",
                            "name": "handoff_human",
                            "arguments": "not-json",
                        }
                    ],
                }
            },
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertFalse(body["results"][0]["result"]["ok"])
        self.assertEqual("VALIDATION", body["results"][0]["result"]["error"]["code"])

    def test_tools_route_invalid_tool_name_keeps_same_envelope(self) -> None:
        settings = Settings(_env_file=None)
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.post(
            "/tools",
            json={
                "message": {
                    "call": {"id": "call_123"},
                    "toolCallList": [
                        {
                            "id": "tc_001",
                            "name": "unknown_tool",
                            "arguments": {"value": 1},
                        }
                    ],
                }
            },
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertFalse(body["results"][0]["result"]["ok"])
        self.assertEqual("tool_name invalido", body["results"][0]["result"]["error"]["message"])

    def test_tools_route_rejects_disabled_authenticate_member_without_provider_call(self) -> None:
        settings = Settings(_env_file=None)
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        with patch(
            "app.tenants.pbsaude.workflows.authenticate_member.get_data_provider"
        ) as get_data_provider:
            response = client.post(
                "/tools",
                json={
                    "message": {
                        "call": {"id": "call_123"},
                        "toolCallList": [
                            {
                                "id": "tc_001",
                                "name": "authenticate_member",
                                "arguments": {
                                    "cpf": "12345678901",
                                    "birthdate": "1990-01-01",
                                },
                            }
                        ],
                    }
                },
            )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertFalse(body["results"][0]["result"]["ok"])
        self.assertEqual("VALIDATION", body["results"][0]["result"]["error"]["code"])
        self.assertEqual("tool_name invalido", body["results"][0]["result"]["error"]["message"])
        get_data_provider.assert_not_called()

    def test_tools_route_rejects_disabled_authorization_status_without_provider_call(self) -> None:
        settings = Settings(_env_file=None)
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        with patch(
            "app.tenants.pbsaude.workflows.get_authorization_status.get_data_provider"
        ) as get_data_provider:
            response = client.post(
                "/tools",
                json={
                    "message": {
                        "call": {"id": "call_123"},
                        "toolCallList": [
                            {
                                "id": "tc_001",
                                "name": "get_authorization_status",
                                "arguments": {
                                    "member_id": "member_123",
                                    "guia_id": "guia_123",
                                },
                            }
                        ],
                    }
                },
            )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertFalse(body["results"][0]["result"]["ok"])
        self.assertEqual("VALIDATION", body["results"][0]["result"]["error"]["code"])
        self.assertEqual("tool_name invalido", body["results"][0]["result"]["error"]["message"])
        get_data_provider.assert_not_called()

    def test_tools_route_rejects_missing_webhook_secret(self) -> None:
        settings = Settings(
            _env_file=None,
            webhook_secret="secret",
            webhook_secret_header="x-webhook-secret",
        )
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.post(
            "/tools",
            json={
                "message": {
                    "call": {"id": "call_123"},
                    "toolCallList": [
                        {
                            "id": "tc_001",
                            "name": "handoff_human",
                            "arguments": {"reason": "fallback"},
                        }
                    ],
                }
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"results": []}, response.json())

    def test_tools_route_rejects_wrong_webhook_secret(self) -> None:
        settings = Settings(
            _env_file=None,
            webhook_secret="secret",
            webhook_secret_header="x-webhook-secret",
        )
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.post(
            "/tools",
            headers={"x-webhook-secret": "wrong"},
            json={
                "message": {
                    "call": {"id": "call_123"},
                    "toolCallList": [
                        {
                            "id": "tc_001",
                            "name": "handoff_human",
                            "arguments": {"reason": "fallback"},
                        }
                    ],
                }
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"results": []}, response.json())

    def test_tools_route_accepts_correct_webhook_secret(self) -> None:
        settings = Settings(
            _env_file=None,
            tenant_map={"+5511999999999": "tenant_a"},
            webhook_secret="secret",
            webhook_secret_header="x-webhook-secret",
        )
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.post(
            "/tools",
            headers={"x-webhook-secret": "secret"},
            json={
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
            },
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertTrue(body["results"][0]["result"]["ok"])
        self.assertEqual("handoff_human", body["results"][0]["result"]["tool_name"])

    def test_tools_route_rejects_unknown_did_in_production(self) -> None:
        settings = production_settings()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        with patch("app.core.tools.dispatcher.record_call_event"):
            response = client.post(
                "/tools",
                headers={"x-webhook-secret": "secret"},
                json={
                    "message": {
                        "call": {"id": "call_123", "to": "+5511888888888"},
                        "toolCallList": [
                            {
                                "id": "tc_001",
                                "name": "handoff_human",
                                "arguments": {"reason": "fallback"},
                            }
                        ],
                    }
                },
            )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertFalse(body["results"][0]["result"]["ok"])
        self.assertEqual("VALIDATION", body["results"][0]["result"]["error"]["code"])
        self.assertEqual("tenant nao resolvido", body["results"][0]["result"]["error"]["message"])

    def test_tools_route_checks_webhook_before_tenant_rejection_in_production(self) -> None:
        settings = production_settings()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        with patch("app.core.tools.dispatcher.record_call_event"):
            response = client.post(
                "/tools",
                headers={"x-webhook-secret": "wrong"},
                json={
                    "message": {
                        "call": {"id": "call_123", "to": "+5511888888888"},
                        "toolCallList": [
                            {
                                "id": "tc_001",
                                "name": "handoff_human",
                                "arguments": {"reason": "fallback"},
                            }
                        ],
                    }
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"results": []}, response.json())

    def test_tools_route_rejects_missing_did_in_production(self) -> None:
        settings = production_settings()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        with patch("app.core.tools.dispatcher.record_call_event"):
            response = client.post(
                "/tools",
                headers={"x-webhook-secret": "secret"},
                json={
                    "message": {
                        "call": {"id": "call_123"},
                        "toolCallList": [
                            {
                                "id": "tc_001",
                                "name": "handoff_human",
                                "arguments": {"reason": "fallback"},
                            }
                        ],
                    }
                },
            )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertFalse(body["results"][0]["result"]["ok"])
        self.assertEqual("VALIDATION", body["results"][0]["result"]["error"]["code"])
        self.assertEqual("tenant nao resolvido", body["results"][0]["result"]["error"]["message"])

    def test_tools_route_accepts_mapped_did_in_production(self) -> None:
        settings = production_settings()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        with patch("app.core.tools.dispatcher.record_call_event"):
            response = client.post(
                "/tools",
                headers={"x-webhook-secret": "secret"},
                json={
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
                },
            )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertTrue(body["results"][0]["result"]["ok"])
        self.assertEqual("handoff_human", body["results"][0]["result"]["tool_name"])


if __name__ == "__main__":
    unittest.main()
