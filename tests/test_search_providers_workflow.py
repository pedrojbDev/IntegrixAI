import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.config import Settings
from app.core.tools.exceptions import BusinessRuleError
from app.tenants.pbsaude.contracts import Provider
from app.tenants.pbsaude.integration.client import ServiceUnavailable
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
                    Settings(
                        _env_file=None,
                        pbsaude_provider_policy_enabled=True,
                        pbsaude_provider_policy_business_override_enabled=True,
                    ),
                    "call_123",
                    "pbsaude",
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

    async def test_normalizes_dermatologist_before_provider_call(self) -> None:
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
                {"cpf": "03457351538", "cidade": "Salvador", "especialidade": "dermatologista"},
                Settings(_env_file=None),
                "call_dermatologist",
                "pbsaude",
            )

        provider.search_providers.assert_called_once_with(
            "pbsaude", "call_dermatologist", "Salvador", "DERMATOLOGIA", "03457351538", None,
        )

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
            "CARDIOLOGIA",
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
            "CARDIOLOGIA",
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
            "CARDIOLOGIA",
            "03457351538",
            None,
        )

    async def test_applies_city_policy_after_successful_provider_response(self) -> None:
        provider = Mock()
        provider.search_providers.return_value = [
            Provider(
                name="Clínica da API",
                specialty="Cardiologia",
                address="Rua da API, 10",
                city="Salvador",
                neighborhood="Centro",
                phone="(71) 3333-4444",
            )
        ]

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
                    "cidade": "Salvador",
                    "especialidade": "Cardiologia",
                },
                Settings(_env_file=None, pbsaude_provider_policy_enabled=True),
                "call_policy",
                "pbsaude",
            )

        self.assertEqual(CallFinalState.RESOLVIDA_AUTOMATICO, final_state)
        self.assertEqual(1, len(data["providers"]))
        self.assertEqual("Centro Médico Pituba", data["providers"][0]["name"])
        self.assertEqual("in_person", data["providers"][0]["service_mode"])

    async def test_successful_response_matches_policy_against_original_service(self) -> None:
        provider = Mock()
        provider.search_providers.return_value = []
        catalog = Mock(is_enabled=True)
        catalog.resolve.return_value = "MEDICO DO TRABALHO"

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.get_specialty_catalog",
            return_value=catalog,
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args: func(*args)),
        ):
            data, final_state = await search_providers(
                {
                    "cpf": "03457351538",
                    "cidade": "Vitoria da Conquista",
                    "especialidade": "Médico da Família",
                },
                Settings(_env_file=None, pbsaude_provider_policy_enabled=True),
                "call_original_service",
                "pbsaude",
            )

        self.assertEqual(CallFinalState.RESOLVIDA_AUTOMATICO, final_state)
        self.assertEqual("online", data["providers"][0]["service_mode"])
        provider.search_providers.assert_called_once_with(
            "pbsaude",
            "call_original_service",
            "Vitoria da Conquista",
            "MEDICO DO TRABALHO",
            "03457351538",
            None,
        )

    async def test_known_business_error_uses_tenant_scoped_static_override(self) -> None:
        provider = Mock()
        business_error = BusinessRuleError(
            code="CIDADE_SEM_COBERTURA",
            message="Não há rede credenciada nessa cidade",
        )

        provider.search_providers.side_effect = business_error
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
                    "cidade": "Vitoria da Conquista",
                    "especialidade": "Médico da Família",
                },
                Settings(
                    _env_file=None,
                    pbsaude_provider_policy_enabled=True,
                    pbsaude_provider_policy_business_override_enabled=True,
                ),
                "call_business_override",
                "pbsaude",
            )

        self.assertEqual(CallFinalState.RESOLVIDA_AUTOMATICO, final_state)
        self.assertEqual(1, len(data["providers"]))
        self.assertEqual("online", data["providers"][0]["service_mode"])
        self.assertEqual("", data["providers"][0]["address"])
        self.assertIsNone(data["providers"][0]["neighborhood"])

    async def test_known_business_error_does_not_override_for_other_tenant(self) -> None:
        business_error = BusinessRuleError(
            code="CIDADE_SEM_COBERTURA",
            message="Não há rede credenciada nessa cidade",
        )

        provider = Mock()
        provider.search_providers.side_effect = business_error
        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args: func(*args)),
        ):
            with self.assertRaises(BusinessRuleError) as exc:
                await search_providers(
                    {
                        "cpf": "03457351538",
                        "cidade": "Vitoria da Conquista",
                        "especialidade": "Médico da Família",
                    },
                    Settings(
                        _env_file=None,
                        pbsaude_provider_policy_enabled=True,
                        pbsaude_provider_policy_business_override_enabled=True,
                    ),
                    "call_other_tenant",
                    "tenant_other",
                )

        self.assertEqual("CIDADE_SEM_COBERTURA", exc.exception.code)
        self.assertEqual("offer_handoff", exc.exception.details["recovery_action"])
        self.assertFalse(exc.exception.retryable)

    async def test_upstream_failure_never_invokes_static_policy_fallback(self) -> None:
        provider = Mock()
        provider.search_providers.side_effect = ServiceUnavailable("API indisponível")

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args: func(*args)),
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.apply_provider_policy",
        ) as policy:
            with self.assertRaisesRegex(RuntimeError, "API indisponível"):
                await search_providers(
                    {
                        "cpf": "03457351538",
                        "cidade": "Salvador",
                        "especialidade": "Cardiologia",
                    },
                    Settings(
                        _env_file=None,
                        pbsaude_provider_policy_enabled=True,
                        pbsaude_provider_policy_business_override_enabled=True,
                    ),
                    "call_upstream_failure",
                    "pbsaude",
                )

        policy.assert_not_called()

    async def test_upstream_business_rule_never_invokes_static_policy_fallback(self) -> None:
        provider = Mock()
        provider.search_providers.side_effect = BusinessRuleError(
            code="SEM_COBERTURA",
            message="Beneficiário sem cobertura",
        )

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread",
            new=AsyncMock(side_effect=provider.search_providers.side_effect),
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.apply_provider_policy",
        ) as policy:
            with self.assertRaises(BusinessRuleError):
                await search_providers(
                    {
                        "cpf": "03457351538",
                        "cidade": "Salvador",
                        "especialidade": "Cardiologia",
                    },
                    Settings(
                        _env_file=None,
                        pbsaude_provider_policy_enabled=True,
                        pbsaude_provider_policy_business_override_enabled=True,
                    ),
                    "call_business_rule",
                    "pbsaude",
                )

        policy.assert_not_called()

    async def test_upstream_timeout_never_invokes_static_policy_fallback(self) -> None:
        provider = Mock()

        with patch(
            "app.tenants.pbsaude.workflows.search_providers.get_data_provider",
            return_value=provider,
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread",
            new=AsyncMock(side_effect=asyncio.TimeoutError),
        ), patch(
            "app.tenants.pbsaude.workflows.search_providers.apply_provider_policy",
        ) as policy:
            with self.assertRaisesRegex(TimeoutError, "Timeout na busca de rede"):
                await search_providers(
                    {
                        "cpf": "03457351538",
                        "cidade": "Salvador",
                        "especialidade": "Cardiologia",
                    },
                    Settings(
                        _env_file=None,
                        pbsaude_provider_policy_enabled=True,
                        pbsaude_provider_policy_business_override_enabled=True,
                    ),
                    "call_timeout",
                    "pbsaude",
                )

        policy.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class SearchClarificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_eye_exam_requests_clarification_without_upstream(self):
        provider = Mock()
        with patch('app.tenants.pbsaude.workflows.search_providers.get_data_provider', return_value=provider):
            with self.assertRaises(BusinessRuleError) as error:
                await search_providers({'cpf': '12345678901', 'cidade': 'Salvador',
                    'especialidade': 'exame de vista'}, Settings(_env_file=None), 'call', 'tenant_a')
        self.assertEqual('collect_especialidade', error.exception.details['recovery_action'])
        self.assertIn('consulta', error.exception.details['clarification_question'])
        self.assertIn('exame', error.exception.details['clarification_question'])
        provider.search_providers.assert_not_called()

    async def test_unknown_exams_are_blocked_when_authoritative_catalog_is_loaded(self):
        for exam in ('urofluxometria', 'eletroneuromiografia', 'exame de urofluxometria'):
            with self.subTest(exam=exam), tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / 'especialidades.csv'
                path.write_text('BAQ_DESCRI\nMAMOGRAFIA\n', encoding='utf-8')
                provider = Mock()
                with patch(
                    'app.tenants.pbsaude.workflows.search_providers.get_data_provider',
                    return_value=provider,
                ), patch(
                    'app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread',
                    new=AsyncMock(side_effect=lambda func, *args: func(*args)),
                ):
                    with self.assertRaises(BusinessRuleError) as error:
                        await search_providers(
                            {
                                'cpf': '03457351538',
                                'cidade': 'Salvador',
                                'especialidade': exam,
                            },
                            Settings(_env_file=None, specialties_csv_path=str(path)),
                            f'call-{exam}',
                            'pbsaude',
                        )
                self.assertEqual('ESPECIALIDADE_INVALIDA', error.exception.code)
                provider.search_providers.assert_not_called()

    async def test_pending_unknown_exams_are_blocked_before_catalog_confirmation(self):
        for exam in ('urofluxometria', 'eletroneuromiografia', 'exame de urofluxometria'):
            with self.subTest(exam=exam):
                provider = Mock()
                with patch(
                    'app.tenants.pbsaude.workflows.search_providers.get_data_provider',
                    return_value=provider,
                ), patch(
                    'app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread',
                    new=AsyncMock(side_effect=lambda func, *args: func(*args)),
                ):
                    with self.assertRaises(BusinessRuleError) as error:
                        await search_providers(
                            {
                                'cpf': '03457351538',
                                'cidade': 'Salvador',
                                'especialidade': exam,
                            },
                            Settings(_env_file=None),
                            f'call-pending-{exam}',
                            'pbsaude',
                        )
                self.assertEqual('ESPECIALIDADE_INVALIDA', error.exception.code)
                provider.search_providers.assert_not_called()
