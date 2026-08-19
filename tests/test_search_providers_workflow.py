import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.config import Settings
from app.core.tools.exceptions import BusinessRuleError
from app.tenants.pbsaude.workflows.search_providers import search_providers
from app.utils.enums import CallFinalState


class SearchProvidersWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_invalid_cpf_before_provider_call(self) -> None:
        provider = Mock()

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ):
            with self.assertRaises(BusinessRuleError) as exc:
                await search_providers(
                    {
                        "cpf": "123",
                        "cidade": "feira de santana",
                        "especialidade": "cardiologia",
                    },
                    Settings(_env_file=None),
                    "call_123",
                    "tenant_a",
                )

        self.assertEqual("CPF_INVALIDO", exc.exception.code)
        provider.search_providers.assert_not_called()

    async def test_rejects_blank_city_before_provider_call(self) -> None:
        provider = Mock()

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ):
            with self.assertRaises(BusinessRuleError) as exc:
                await search_providers(
                    {
                        "cpf": "03457351538",
                        "cidade": "   ",
                        "especialidade": "cardiologia",
                    },
                    Settings(_env_file=None),
                    "call_123",
                    "tenant_a",
                )

        self.assertEqual("CIDADE_INVALIDA", exc.exception.code)
        provider.search_providers.assert_not_called()

    async def test_accepts_blank_legacy_neighborhood_without_forwarding_it(self) -> None:
        provider = Mock()
        provider.search_providers.return_value = []

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args: func(*args)),
        ):
            data, final_state = await search_providers(
                {
                    "cpf": "03457351538",
                    "cidade": " feira de santana ",
                    "especialidade": " cardiologia ",
                    "bairro": "",
                },
                Settings(_env_file=None),
                "call_123",
                "tenant_a",
            )

        self.assertEqual(CallFinalState.RESOLVIDA_AUTOMATICO, final_state)
        self.assertEqual({"providers": []}, data)
        provider.search_providers.assert_called_once_with(
            "tenant_a",
            "call_123",
            "feira de santana",
            "cardiologia",
            "03457351538",
            None,
        )

    async def test_accepts_nonblank_legacy_neighborhood_without_forwarding_it(self) -> None:
        provider = Mock()
        provider.search_providers.return_value = []

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args: func(*args)),
        ):
            await search_providers(
                {
                    "cpf": "03457351538",
                    "cidade": "feira de santana",
                    "especialidade": "cardiologia",
                    "bairro": "Centro",
                },
                Settings(_env_file=None),
                "call_legacy",
                "tenant_a",
            )

        provider.search_providers.assert_called_once_with(
            "tenant_a",
            "call_legacy",
            "feira de santana",
            "cardiologia",
            "03457351538",
            None,
        )

    async def test_accepts_request_without_legacy_neighborhood(self) -> None:
        provider = Mock()
        provider.search_providers.return_value = []

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args: func(*args)),
        ):
            data, final_state = await search_providers(
                {
                    "cpf": "03457351538",
                    "cidade": "feira de santana",
                    "especialidade": "cardiologia",
                },
                Settings(_env_file=None),
                "call_without_neighborhood",
                "tenant_a",
            )

        self.assertEqual(CallFinalState.RESOLVIDA_AUTOMATICO, final_state)
        self.assertEqual({"providers": []}, data)
        provider.search_providers.assert_called_once_with(
            "tenant_a",
            "call_without_neighborhood",
            "feira de santana",
            "cardiologia",
            "03457351538",
            None,
        )


if __name__ == "__main__":
    unittest.main()
