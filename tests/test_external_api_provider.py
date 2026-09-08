import unittest
from unittest.mock import MagicMock, patch

import httpx

from app.config import Settings
from app.core.tools.exceptions import BusinessRuleError
from app.tenants.pbsaude.integration.client import ServiceUnavailable
from app.tenants.pbsaude.integration.external_api_provider import ExternalApiDataProvider
from app.tenants.pbsaude.integration.http_client import (
    close_external_api_client,
    get_external_api_client,
)


def settings(**overrides):
    values = {
        "_env_file": None,
        "external_api_base_url": "https://api.customer-prod.internal",
        "external_api_auth_type": "none",
        "external_api_max_retries": 1,
        "external_api_retry_backoff_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


def success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "success": True,
            "prestadores": [
                {
                    "nome": "Clinica Alpha",
                    "endereco": "Rua A, 10",
                    "bairro": "Centro",
                    "telefone": "75991289484",
                }
            ],
        },
    )


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ExternalApiProviderTests(unittest.TestCase):
    def tearDown(self) -> None:
        close_external_api_client()

    def test_reuses_shared_http_client(self) -> None:
        client = MagicMock()

        with patch(
            "app.tenants.pbsaude.integration.http_client.httpx.Client",
            return_value=client,
        ) as client_factory:
            first = get_external_api_client(settings())
            second = get_external_api_client(settings())

        self.assertIs(first, second)
        client_factory.assert_called_once()

    def test_retries_transient_http_then_returns_success(self) -> None:
        fake_client = FakeClient([httpx.Response(503), success_response()])
        provider = ExternalApiDataProvider(settings())

        with patch(
            "app.tenants.pbsaude.integration.http_client.get_external_api_client",
            return_value=fake_client,
        ):
            providers = provider.search_providers(
                "tenant_a",
                "call_123",
                "feira de santana",
                "cardiologia",
                "03457351538",
                None,
            )

        self.assertEqual(2, len(fake_client.calls))
        self.assertEqual("Clínica Alpha", providers[0].name)

    def test_retries_http_500_then_returns_success(self) -> None:
        fake_client = FakeClient([httpx.Response(500), success_response()])
        provider = ExternalApiDataProvider(settings())

        with patch(
            "app.tenants.pbsaude.integration.http_client.get_external_api_client",
            return_value=fake_client,
        ):
            providers = provider.search_providers(
                "tenant_a",
                "call_123",
                "feira de santana",
                "cardiologia",
                "03457351538",
                None,
            )

        self.assertEqual(2, len(fake_client.calls))
        self.assertEqual("Clínica Alpha", providers[0].name)

    def test_retries_malformed_json_success_response_then_returns_success(self) -> None:
        fake_client = FakeClient([httpx.Response(200, content=b"not-json"), success_response()])
        provider = ExternalApiDataProvider(settings())

        with patch(
            "app.tenants.pbsaude.integration.http_client.get_external_api_client",
            return_value=fake_client,
        ):
            providers = provider.search_providers(
                "tenant_a",
                "call_123",
                "feira de santana",
                "cardiologia",
                "03457351538",
                None,
            )

        self.assertEqual(2, len(fake_client.calls))
        self.assertEqual("Clínica Alpha", providers[0].name)

    def test_sends_search_payload_without_neighborhood(self) -> None:
        fake_client = FakeClient([success_response()])
        provider = ExternalApiDataProvider(settings())

        with patch(
            "app.tenants.pbsaude.integration.http_client.get_external_api_client",
            return_value=fake_client,
        ):
            provider.search_providers(
                "tenant_a",
                "call_123",
                " feira de santana ",
                " cardiologia ",
                "034.573.515-38",
                None,
            )

        self.assertEqual(
            {
                "cpf": "03457351538",
                "especialidade": "cardiologia",
                "cidade": "feira de santana",
            },
            fake_client.calls[0]["kwargs"]["json"],
        )

    def test_request_error_retries_until_limit_then_fails(self) -> None:
        fake_client = FakeClient(
            [
                httpx.ConnectError("connect failed"),
                httpx.ConnectError("connect failed"),
            ]
        )
        provider = ExternalApiDataProvider(settings())

        with patch(
            "app.tenants.pbsaude.integration.http_client.get_external_api_client",
            return_value=fake_client,
        ):
            with self.assertRaises(ServiceUnavailable):
                provider.search_providers(
                    "tenant_a",
                    "call_123",
                    "feira de santana",
                    "cardiologia",
                    "03457351538",
                    None,
                )

        self.assertEqual(2, len(fake_client.calls))

    def test_business_error_does_not_retry(self) -> None:
        fake_client = FakeClient(
            [
                httpx.Response(
                    400,
                    json={
                        "errorCode": "ESPECIALIDADE_INVALIDA",
                        "field": "especialidade",
                        "message": "Especialidade invalida",
                    },
                ),
                success_response(),
            ]
        )
        provider = ExternalApiDataProvider(settings())

        with patch(
            "app.tenants.pbsaude.integration.http_client.get_external_api_client",
            return_value=fake_client,
        ):
            with self.assertRaises(BusinessRuleError):
                provider.search_providers(
                    "tenant_a",
                    "call_123",
                    "feira de santana",
                    "cardiologia",
                    "03457351538",
                    None,
                )

        self.assertEqual(1, len(fake_client.calls))

    def test_non_transient_http_does_not_retry(self) -> None:
        fake_client = FakeClient([httpx.Response(401), success_response()])
        provider = ExternalApiDataProvider(settings())

        with patch(
            "app.tenants.pbsaude.integration.http_client.get_external_api_client",
            return_value=fake_client,
        ):
            with self.assertRaises(ServiceUnavailable):
                provider.search_providers(
                    "tenant_a",
                    "call_123",
                    "feira de santana",
                    "cardiologia",
                    "03457351538",
                    None,
                )

        self.assertEqual(1, len(fake_client.calls))

    def test_caps_each_attempt_by_the_total_voice_deadline(self) -> None:
        fake_client = FakeClient([success_response()])
        provider = ExternalApiDataProvider(
            settings(external_api_timeout_seconds=8.0, external_api_total_deadline_seconds=0.5)
        )

        with patch(
            "app.tenants.pbsaude.integration.http_client.get_external_api_client",
            return_value=fake_client,
        ):
            provider.search_providers(
                "tenant_a",
                "call_123",
                "feira de santana",
                "cardiologia",
                "03457351538",
                None,
            )

        self.assertLessEqual(fake_client.calls[0]["kwargs"]["timeout"], 0.5)

    def test_retry_attempt_uses_only_remaining_voice_deadline(self) -> None:
        fake_client = FakeClient([httpx.Response(500), success_response()])
        provider = ExternalApiDataProvider(
            settings(external_api_timeout_seconds=3.0, external_api_total_deadline_seconds=4.0)
        )

        with (
            patch(
                "app.tenants.pbsaude.integration.http_client.get_external_api_client",
                return_value=fake_client,
            ),
            patch(
                "app.tenants.pbsaude.integration.http_client.time.monotonic",
                side_effect=[100.0, 100.0, 100.0, 100.0, 103.75],
            ),
        ):
            provider.search_providers(
                "tenant_a",
                "call_123",
                "feira de santana",
                "cardiologia",
                "03457351538",
                None,
            )

        self.assertEqual(2, len(fake_client.calls))
        self.assertEqual(3.0, fake_client.calls[0]["kwargs"]["timeout"])
        self.assertEqual(0.25, fake_client.calls[1]["kwargs"]["timeout"])

    def test_logs_attempt_without_full_cpf(self) -> None:
        fake_client = FakeClient([success_response()])
        provider = ExternalApiDataProvider(settings())

        with (
            patch(
                "app.tenants.pbsaude.integration.http_client.get_external_api_client",
                return_value=fake_client,
            ),
            patch("app.tenants.pbsaude.integration.http_client.log") as log,
        ):
            provider.search_providers(
                "tenant_a",
                "call_123",
                "feira de santana",
                "cardiologia",
                "03457351538",
                None,
            )

        log.info.assert_called_once()
        log_text = str(log.info.call_args)
        self.assertIn("call_123", log_text)
        self.assertNotIn("03457351538", log_text)


if __name__ == "__main__":
    unittest.main()
