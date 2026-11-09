"""Urgent-care workflow through the real customer API adapter, with local HTTP."""
import json
import unittest
from unittest.mock import patch

import httpx

from app.config import Settings
from app.core.tools.exceptions import BusinessRuleError, UpstreamToolError
from app.tenants.pbsaude.workflows.search_providers import search_providers


class UrgentCareSearchTests(unittest.IsolatedAsyncioTestCase):
    async def search(self, response, query='emergência'):
        requests = []

        def handle(request):
            requests.append(request)
            if isinstance(response, Exception):
                raise response
            return response

        settings = Settings(_env_file=None, data_mode='external_api', db_enabled=False,
            external_api_base_url='https://pbsaude.test', external_api_auth_type='none',
            external_api_max_retries=0, pbsaude_provider_policy_enabled=True,
            pbsaude_provider_policy_business_override_enabled=True)
        with httpx.Client(transport=httpx.MockTransport(handle)) as client, patch(
            'app.tenants.pbsaude.integration.http_client.get_external_api_client', return_value=client):
            try:
                result = await search_providers(
                    {'cpf': '12345678901', 'city': 'Salvador', 'query': query},
                    settings, 'call-urgent-test', 'pbsaude')
            finally:
                self.assertEqual(1, len(requests))
                self.assertEqual('pbsaude.test', requests[0].url.host)
                self.assertEqual({'cpf': '12345678901', 'cidade': 'Salvador',
                                  'especialidade': 'PRONTO ATENDIMENTO'}, json.loads(requests[0].content))
        return result

    async def test_returns_real_presential_provider_for_urgent_request(self):
        result, _ = await self.search(httpx.Response(200, json={'success': True, 'prestadores': [
            {'nome': 'Hospital Teste', 'endereco': 'Avenida Teste, 10', 'cidade': 'Salvador',
             'telefone': '7133334444'}]}))
        self.assertEqual(1, len(result['providers']))
        self.assertEqual('Hospital Teste', result['providers'][0]['name'])
        self.assertEqual('PRONTO ATENDIMENTO', result['providers'][0]['specialty'])
        self.assertEqual('Salvador', result['providers'][0]['city'])

    async def test_empty_success_stays_empty_without_inventing_online_provider(self):
        result, _ = await self.search(httpx.Response(200, json={'success': True, 'prestadores': []}), query='urgência')
        self.assertEqual({'providers': []}, result)

    async def test_city_without_network_preserves_business_code_for_prompt_exception(self):
        with self.assertRaises(BusinessRuleError) as raised:
            await self.search(httpx.Response(422, json={'success': False,
                'errorCode': 'CIDADE_SEM_COBERTURA', 'message': 'Sem rede nessa cidade'}))
        self.assertEqual('CIDADE_SEM_COBERTURA', raised.exception.code)

    async def test_bad_city_or_specialty_does_not_become_absence_of_network(self):
        for code, field in (('CIDADE_INVALIDA', 'cidade'), ('ESPECIALIDADE_INVALIDA', 'especialidade'),
                            ('CPF_INVALIDO', 'cpf')):
            with self.subTest(code=code), self.assertRaises(BusinessRuleError) as raised:
                await self.search(httpx.Response(422, json={'success': False,
                    'errorCode': code, 'field': field, 'message': 'Dado invalido'}))
            self.assertEqual(code, raised.exception.code)

    async def test_technical_failures_do_not_become_empty_network(self):
        for status, expected in ((401, 'UPSTREAM_AUTH'), (503, 'UPSTREAM_5XX')):
            with self.subTest(status=status), self.assertRaises(UpstreamToolError) as raised:
                await self.search(httpx.Response(status))
            self.assertEqual(expected, raised.exception.upstream_code)
        with self.assertRaises(TimeoutError):
            await self.search(httpx.ReadTimeout('test timeout'))
