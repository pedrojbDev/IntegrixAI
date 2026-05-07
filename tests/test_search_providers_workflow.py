import unittest
from unittest.mock import Mock, patch

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

    async def test_normalizes_blank_neighborhood_to_none(self) -> None:
        provider = Mock(return_value=[])
        provider.search_providers.return_value = []

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
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
        provider.search_providers.assert_called_once()
        self.assertIsNone(provider.search_providers.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
