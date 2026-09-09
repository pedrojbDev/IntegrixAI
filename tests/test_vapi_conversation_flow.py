import copy
import json
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.tools.dispatcher import ToolDispatcher
from app.core.tools.registry import TenantToolRegistry
from app.db import Base
from app.models.call_event import CallEvent
from app.models.vapi_call_slot_state import VapiCallSlotState
from app.models.tool_invocation import ToolBusinessErrorAttempt
from app.platform.services.vapi_event_ingestion import VapiEventIngestionService
from app.platform.services.vapi_conversation import keyed_hmac
from app.tenants.pbsaude.catalog import get_specialty_catalog
from app.tenants.pbsaude.slot_guard import validate_search_slot_provenance, recovery_attempt
from app.tenants.pbsaude.tool_handlers import register_pbsaude_handlers
from app.core.tools.exceptions import BusinessRuleError

CPF = '12345678901'


class ConversationFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)
        self.settings = Settings(_env_file=None, db_enabled=True, webhook_secret='test',
            vapi_slot_guard_enabled=True, vapi_slot_state_hmac_secret='test-evidence-key',
            tenant_map={'+551100000001': 'tenant_a', '+551100000002': 'tenant_b'})
        self.registry = register_pbsaude_handlers(TenantToolRegistry())
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module in ['app.tenants.pbsaude.slot_guard', 'app.tenants.pbsaude.tool_handlers',
                       'app.core.tools.idempotency']:
            self.stack.enter_context(patch(module+'.SessionLocal', self.sessions))
        self.audit = self.stack.enter_context(patch('app.core.tools.dispatcher.record_call_event'))
        self.stack.enter_context(patch('app.core.tools.dispatcher.metrics_store.record'))
        self.provider = MagicMock()
        self.provider.search_providers.return_value = []
        self.stack.enter_context(patch('app.tenants.pbsaude.workflows.search_providers.get_data_provider', return_value=self.provider))
        self.base = int(datetime.now(timezone.utc).timestamp()*1000)-100000

    def messages(self, *utterances):
        return [{'role': role, 'message': text, 'time': self.base+i*1000} for i,(role,text) in enumerate(utterances)]

    def payload(self, messages, rev=1, tenant='tenant_a', tools=None):
        return {'message': {'type': 'tool-calls' if tools else 'conversation-update',
            'timestamp': self.base+50000+rev,
            'call': {'id': 'same-call', 'to': '+551100000001' if tenant=='tenant_a' else '+551100000002'},
            'artifact': {'messages': messages}, 'toolCallList': tools or []}}

    def ingest(self, messages, rev=1, tenant='tenant_a'):
        with self.sessions() as session:
            return VapiEventIngestionService(self.settings).ingest(session, self.payload(messages,rev,tenant))

    def state(self, tenant='tenant_a'):
        with self.sessions() as session:
            return session.get(VapiCallSlotState, {'tenant_id':tenant,'call_id':'same-call'})

    def validate(self, city='Salvador', query='Cardiologia', tenant='tenant_a', cpf=CPF):
        validate_search_slot_provenance(settings=self.settings, tenant_id=tenant, call_id='same-call',
            cpf=cpf, city=city, query=query, catalog=get_specialty_catalog(self.settings))

    def tool(self, id='tc1', city='Salvador', query='Cardiologia'):
        return {'id':id,'function':{'name':'search_providers','arguments':{'cpf':CPF,'city':city,'query':query}}}

    def direct_search(self, city='Salvador', query='Cardiologia', tenant='tenant_a'):
        from app.tenants.pbsaude.workflows.search_providers import _search_providers
        return _search_providers(
            self.tool(city=city, query=query)['function']['arguments'],
            self.settings,
            'same-call',
            tenant,
        )

    async def dispatch(self, messages, tools, rev=1, authorized=True):
        request=SimpleNamespace(headers={'x-webhook-secret':'test'} if authorized else {})
        return await ToolDispatcher(self.settings,self.registry).dispatch(request,self.payload(messages,rev,tools=tools))

    def standard(self):
        return self.messages(('bot','Digite o CPF no teclado.'), ('user',f"User's Keypad Entry: {CPF}#"),
            ('bot','Pode me falar a cidade para atendimento?'),('user','Salvador, Bahia.'),
            ('bot','Qual especialidade ou tipo de exame você procura?'),('user','Cardiologista'))

    async def test_cpf_only_never_calls_provider_or_consumes_attempt(self):
        messages=self.standard()[:2]
        for i in range(3):
            result=(await self.dispatch(messages,[self.tool(id=f'tc{i}')]))['results'][0]['result']
            self.assertFalse(result['ok']);self.assertEqual(0,result['data']['attempt'])
            self.assertTrue(result['data']['retryable'])
        self.provider.search_providers.assert_not_called()
        with self.sessions() as session:self.assertIsNone(session.scalar(select(ToolBusinessErrorAttempt)))

    def test_city_correction_preserves_specialties_and_rejects_old_city(self):
        ms=self.messages(('user',f"User's Keypad Entry: {CPF}"),('bot','Pode me falar a cidade?'),
            ('user','Verde Santana'),('bot','Pode repetir a cidade?'),('user','Feira de Santana, Bahia'),
            ('bot','Qual especialidade?'),('user','Urologista'))
        self.ingest(ms)
        self.validate('Feira de Santana','Urologia')
        with self.assertRaises(BusinessRuleError):self.validate('Verde Santana','Urologia')
        # An invented tool argument must not destroy valid evidence.
        self.validate('Feira de Santana','Urologia')

    def test_repeated_city_after_recovery_is_a_new_turn(self):
        ms=self.standard();self.ingest(ms)
        with self.assertRaises(BusinessRuleError):self.validate('João Pessoa')
        ms+=self.messages(('bot','Pode repetir a cidade?'),('user','Salvador, Bahia.'))
        ms[-2]['time']=self.base+10000;ms[-1]['time']=self.base+11000
        self.ingest(ms,rev=2);self.validate()
        self.assertEqual(8,len(self.state().conversation_meta['turns']))

    def test_three_requests_and_acknowledgements_preserve_all_evidence(self):
        ms=self.standard()[:-1]+self.messages(('user','Exames de sangue, ginecologista e oftalmologista'))
        ms[-1]['time']=self.base+5000
        for i,(role,text) in enumerate([('bot','Você quer todos?'),('user','Todos os três'),
            ('bot','Só para confirmar: você quer laboratório, certo?'),('user','Isso')],6):
            ms.append({'role':role,'message':text,'time':self.base+i*1000})
        self.ingest(ms)
        for query in ['Laboratório','Ginecologia','Oftalmologia']:self.validate(query=query)

    def test_spontaneous_data_before_keypad_is_preserved(self):
        ms=self.messages(('user','Preciso de cardiologista em Salvador'),
            ('bot','Digite o CPF no teclado.'),('user',f"User's Keypad Entry: {CPF}#"))
        self.ingest(ms);self.validate()

    def test_greeting_does_not_fill_city_and_spoken_cpf_is_rejected(self):
        ms=self.messages(('user',f'Meu CPF é {CPF}'),('user','Salvador'),('user','Cardiologista'))
        self.ingest(ms)
        with self.assertRaises(BusinessRuleError):self.validate()
        ms=self.standard()[:2]+[{'role':'user','message':'Alô?','time':self.base+2000}]
        self.ingest(ms,rev=2)
        self.assertFalse(self.state().city_term_hmacs)

    def test_duplicate_and_out_of_order_revision_cannot_restore_wrong_city(self):
        ms=self.standard();ms[3]['message']='Verde Santana'
        self.ingest(ms,rev=1)
        corrected=copy.deepcopy(ms);corrected[3]['message']='Salvador, Bahia'
        self.ingest(corrected,rev=3)
        old=copy.deepcopy(ms);old[3]['message']='Outra cidade'
        self.ingest(old,rev=2);self.validate()
        before=self.state().conversation_meta['revision']
        self.ingest(corrected,rev=3)
        self.assertEqual(before,self.state().conversation_meta['revision'])

    def test_handoff_question_does_not_reopen_city(self):
        ms=self.standard()+[{'role':'bot','message':'Posso transferir para um atendente humano?', 'time':self.base+6000},
            {'role':'user','message':'Alô?', 'time':self.base+7000}]
        self.ingest(ms);self.validate();self.assertEqual('handoff',self.state().phase)

    def test_tenant_isolation_and_no_plaintext_evidence(self):
        self.ingest(self.standard());self.ingest(self.standard()[:2],tenant='tenant_b')
        self.validate()
        with self.assertRaises(BusinessRuleError):self.validate(tenant='tenant_b')
        stored=json.dumps(self.state().conversation_meta)
        for text in [CPF,'Salvador','Cardiologista','Digite']:self.assertNotIn(text,stored)

    async def test_tools_history_arriving_first_is_ingested_and_batch_is_serial(self):
        result=await self.dispatch(self.standard(),[self.tool(),self.tool('tc2'),self.tool('tc3')])
        self.assertTrue(result['results'][0]['result']['ok'])
        self.assertEqual(1,self.provider.search_providers.call_count)
        for entry in result['results'][1:]:
            self.assertEqual('wait_current_search',entry['result']['data']['recovery_action'])
            self.assertEqual(0,entry['result']['data']['attempt'])
        # Delivery retry must return the exact saved envelope and not call upstream.
        self.assertEqual(result,await self.dispatch(self.standard(),[self.tool(),self.tool('tc2'),self.tool('tc3')]))
        self.assertEqual(1,self.provider.search_providers.call_count)
        self.ingest(self.standard(),rev=1);self.validate()

    async def test_unauthorized_tools_cannot_update_state(self):
        await self.dispatch(self.standard(),[self.tool()],authorized=False)
        self.assertIsNone(self.state());self.provider.search_providers.assert_not_called()

    async def test_evidence_persistence_failure_fails_closed(self):
        with patch('app.tenants.pbsaude.tool_handlers.capture_pbsaude_conversation',side_effect=RuntimeError('db unavailable')):
            result=await self.dispatch(self.standard(),[self.tool()])
        self.assertFalse(result['results'][0]['result']['ok'])
        self.provider.search_providers.assert_not_called()

    def test_recovery_attempts_count_new_evidence_not_tool_retries(self):
        self.ingest(self.standard())
        def count():return recovery_attempt(settings=self.settings, tenant_id='tenant_a',call_id='same-call',
            field='cidade',code='CIDADE_INVALIDA')
        self.assertEqual(1,count());self.assertEqual(1,count())
        ms=self.standard()+[{'role':'bot','message':'Pode repetir a cidade?', 'time':self.base+6000},
            {'role':'user','message':'Salvador, Bahia.', 'time':self.base+7000}]
        self.ingest(ms,rev=2);self.assertEqual(2,count())

    async def test_started_transfer_blocks_new_search(self):
        self.ingest(self.standard())
        payload=self.payload([]);payload['message'].update(type='status-update',status='forwarding')
        with self.sessions() as session:VapiEventIngestionService(self.settings).ingest(session,payload)
        result=await self.dispatch(self.standard(),[self.tool()])
        self.assertEqual('stop',result['results'][0]['result']['data']['recovery_action'])
        self.provider.search_providers.assert_not_called()

    def test_later_identical_snapshot_protects_against_intermediate_revision(self):
        ms = self.standard()
        self.ingest(ms, rev=1)
        self.ingest(ms, rev=3)
        stale = copy.deepcopy(ms)
        stale[3]['message'] = 'Outra cidade'
        self.ingest(stale, rev=2)
        self.validate()

    def test_two_invalid_keypad_turns_are_not_model_attempts(self):
        ms = self.messages(('bot', 'Digite o CPF no teclado.'),
            ('user', "User's Keypad Entry: 123#"), ('bot', 'Digite novamente o CPF.'),
            ('user', 'Alô?'), ('user', "User's Keypad Entry: 456#"))
        self.ingest(ms)
        self.assertIsNone(self.state().cpf_hmac)
        for _ in range(3):
            self.assertEqual(2, recovery_attempt(settings=self.settings, tenant_id='tenant_a',
                call_id='same-call', field='cpf', code='SLOT_UNCONFIRMED'))

    def test_invalid_keypad_correction_invalidates_previous_cpf(self):
        ms = self.standard() + [{'role': 'user', 'message': "Corrigindo meu CPF: User's Keypad Entry: 123#", 'time': self.base+6000}]
        self.ingest(ms)
        with self.assertRaises(BusinessRuleError):
            self.validate()

    def test_old_or_future_event_cannot_create_evidence(self):
        for stamp in [self.base - 48*3600000, 1e200]:
            payload = self.payload(self.standard())
            payload['message']['timestamp'] = stamp
            with self.sessions() as session:
                VapiEventIngestionService(self.settings).ingest(session, payload)
            self.assertIsNone(self.state())

    async def test_end_before_transcript_is_a_tombstone(self):
        payload = self.payload([])
        payload['message']['type'] = 'end-of-call-report'
        with self.sessions() as session:
            VapiEventIngestionService(self.settings).ingest(session, payload)
        result = await self.dispatch(self.standard(), [self.tool()])
        self.assertEqual('stop', result['results'][0]['result']['data']['recovery_action'])
        self.provider.search_providers.assert_not_called()

    def test_newer_active_status_reopens_failed_transfer_but_never_ended_call(self):
        self.ingest(self.standard())
        def status(kind, rev, value=None):
            payload = self.payload([], rev=rev)
            payload['message'].update(type=kind, status=value)
            with self.sessions() as session:
                VapiEventIngestionService(self.settings).ingest(session, payload)
        status('status-update', 3, 'forwarding')
        status('status-update', 2, 'in-progress')
        with self.assertRaises(BusinessRuleError): self.validate()
        status('status-update', 4, 'in-progress')
        self.validate()
        status('status-update', 1, 'forwarding')
        self.validate()
        status('end-of-call-report', 5)
        status('status-update', 6, 'in-progress')
        with self.assertRaises(BusinessRuleError): self.validate()

    async def test_success_resets_recovery_and_next_specialty_can_be_searched(self):
        self.ingest(self.standard())
        self.assertEqual(1, recovery_attempt(settings=self.settings, tenant_id='tenant_a',
            call_id='same-call', field='cidade', code='CIDADE_INVALIDA'))
        result = await self.dispatch(self.standard(), [self.tool()])
        self.assertTrue(result['results'][0]['result']['ok'])
        self.assertNotIn('recovery_attempts', self.state().conversation_meta)
        ms = self.standard() + [{'role': 'user', 'message': 'Agora quero um urologista na mesma cidade', 'time': self.base+6000}]
        result = await self.dispatch(ms, [self.tool('tc2', query='Urologia')], rev=2)
        self.assertTrue(result['results'][0]['result']['ok'])
        self.assertEqual(2, self.provider.search_providers.call_count)
        with self.assertRaises(BusinessRuleError): self.validate(query='Cardiologia')

    async def test_empty_model_arguments_do_not_count_as_invalid_user_answers(self):
        ms = self.standard()
        for index, field in enumerate(['cpf', 'city', 'query']):
            tool = self.tool(f'missing-{index}')
            tool['function']['arguments'][field] = ''
            result = (await self.dispatch(ms, [tool]))['results'][0]['result']
            self.assertEqual(0, result['data']['attempt'])
            self.assertEqual('SLOT_UNCONFIRMED', result['data']['upstream_code'])
            self.validate()
        self.provider.search_providers.assert_not_called()

    async def test_valid_answer_clears_previous_failed_confirmations(self):
        ms = self.messages(('user', f"User's Keypad Entry: {CPF}#"),
            ('bot', 'Qual cidade?'), ('user', 'Não'), ('user', 'Não'),
            ('user', 'Salvador'), ('bot', 'Qual especialidade?'), ('user', 'Cardiologista'))
        result = (await self.dispatch(ms, [self.tool(city='Cidade inventada')]))['results'][0]['result']
        self.assertEqual(0, result['data']['attempt'])
        self.validate()

    def test_incidental_keypad_keeps_cpf_and_preserves_city_speech(self):
        ms = self.messages(
            ('bot', 'Digite o CPF no teclado.'),
            ('user', f"User's Keypad Entry: {CPF}#"),
            ('bot', 'Pode me falar a cidade para atendimento?'),
            ('user', "User's Keypad Entry: 7# moro em Salvador, Bahia."),
            ('bot', 'Qual especialidade ou tipo de exame você procura?'),
            ('user', 'Cardiologista'),
        )
        self.ingest(ms)
        self.validate()

    def test_explicit_cpf_correction_blocks_old_cpf_until_replacement_is_valid(self):
        replacement = '98765432109'
        ms = self.standard() + [
            {'role': 'user', 'message': 'Preciso corrigir meu CPF.', 'time': self.base + 6000},
            {'role': 'bot', 'message': 'Digite o CPF no teclado.', 'time': self.base + 7000},
        ]
        self.ingest(ms)
        with self.assertRaises(BusinessRuleError):
            self.validate()
        ms.append({'role': 'user', 'message': f"User's Keypad Entry: {replacement}#", 'time': self.base + 8000})
        self.ingest(ms, rev=2)
        self.validate(cpf=replacement)
        with self.assertRaises(BusinessRuleError):
            self.validate()

    def test_confirmation_for_known_city_cannot_authorize_it_as_specialty(self):
        ms = self.messages(
            ('bot', 'Digite o CPF no teclado.'),
            ('user', f"User's Keypad Entry: {CPF}#"),
            ('bot', 'Pode me falar a cidade para atendimento?'),
            ('user', 'Salvador, Bahia.'),
            ('bot', 'Qual especialidade ou tipo de exame você procura?'),
            ('bot', 'Você quis dizer Salvador, certo?'),
            ('user', 'Sim'),
            ('user', 'Cardiologista'),
        )
        self.ingest(ms)
        self.validate()
        with self.assertRaises(BusinessRuleError):
            self.validate(query='Salvador')

    def test_cpf_error_statement_blocks_the_previous_cpf(self):
        ms = self.standard() + [
            {'role': 'user', 'message': 'Meu CPF está errado, digitei errado.', 'time': self.base + 6000},
        ]
        self.ingest(ms)
        with self.assertRaises(BusinessRuleError):
            self.validate()

    def test_cpf_replacement_statement_blocks_the_previous_cpf(self):
        ms = self.standard() + [
            {'role': 'user', 'message': 'O CPF correto é outro.', 'time': self.base + 6000},
        ]
        self.ingest(ms)
        with self.assertRaises(BusinessRuleError):
            self.validate()

    def test_negated_cpf_change_keeps_the_confirmed_cpf(self):
        ms = self.standard() + [
            {'role': 'user', 'message': 'Não quero mudar meu CPF.', 'time': self.base + 6000},
        ]
        self.ingest(ms)
        self.validate()

    def test_later_hearing_question_does_not_consume_city_readback_confirmation(self):
        ms = self.messages(
            ('bot', 'Digite o CPF no teclado.'),
            ('user', f"User's Keypad Entry: {CPF}#"),
            ('bot', 'Pode me falar a cidade para atendimento?'),
            ('user', 'Feira de Santana'),
            ('bot', 'Você quis dizer Feira, certo? Está me ouvindo?'),
            ('user', 'Sim'),
            ('bot', 'Qual especialidade ou tipo de exame você procura?'),
            ('user', 'Cardiologista'),
        )
        self.ingest(ms)
        self.validate(city='Feira de Santana')

    def test_keypad_turn_with_cpf_mention_keeps_city_and_specialty_speech(self):
        ms = self.messages(
            ('bot', 'Digite o CPF no teclado.'),
            ('user', f"User's Keypad Entry: {CPF}# Esse é meu CPF, moro em Salvador e preciso de cardiologista."),
        )
        self.ingest(ms)
        self.validate()

    def extended(self, *utterances):
        messages = self.standard()
        messages.extend({'role': role, 'message': text, 'time': self.base + (6+i)*1000}
                        for i, (role, text) in enumerate(utterances))
        return messages

    def test_corrected_city_readback_can_replace_misheard_value(self):
        ms = self.standard()
        ms[3]['message'] = 'Tamafari'
        ms[4:4] = [{'role': 'bot', 'message': 'A cidade é Camaçari, certo?', 'time': self.base+3100},
                   {'role': 'user', 'message': 'Sim', 'time': self.base+3200}]
        self.ingest(ms)
        self.validate(city='Camaçari')
        with self.assertRaises(BusinessRuleError): self.validate(city='Tamafari')

    def test_negative_city_confirmation_revokes_only_city(self):
        self.ingest(self.extended(('bot', 'A cidade é Salvador, certo?'), ('user', 'Não')))
        state = self.state()
        self.assertFalse(state.city_term_hmacs)
        self.assertTrue(state.specialty_term_hmacs)
        self.assertIsNotNone(state.cpf_hmac)
        self.assertEqual(1, state.conversation_meta['failures']['cidade'])

    def test_negated_specialty_replacement_removes_old_request(self):
        self.ingest(self.extended(('user', 'Não quero cardiologista, quero urologista')))
        self.validate(query='Urologia')
        with self.assertRaises(BusinessRuleError): self.validate(query='Cardiologia')

    def test_trailing_courtesy_preserves_city_confirmation(self):
        ms = self.standard()
        ms[3]['message'] = 'Tamafari'
        ms[4:4] = [{'role': 'bot', 'message': 'A cidade é Camaçari, certo? Por favor.', 'time': self.base+3100},
                   {'role': 'user', 'message': 'Sim', 'time': self.base+3200}]
        self.ingest(ms)
        self.validate(city='Camaçari')

    def test_real_hearing_question_prevents_corrected_city_assent(self):
        self.ingest(self.extended(('bot', 'A cidade é Camaçari, certo? Está me ouvindo?'), ('user', 'Sim')))
        self.validate()
        with self.assertRaises(BusinessRuleError): self.validate(city='Camaçari')

    def test_removal_preserves_other_requests_and_their_order(self):
        ms = self.extended(('user', 'Quero ginecologista e oftalmologista'),
                           ('user', 'Retire cardiologista'))
        self.ingest(ms)
        for query in ['Ginecologia', 'Oftalmologia']: self.validate(query=query)
        with self.assertRaises(BusinessRuleError): self.validate(query='Cardiologia')
        requests = self.state().conversation_meta['active_requests']
        self.assertEqual([keyed_hmac(self.settings.vapi_slot_state_hmac_secret, term)
                          for term in ['ginecologia', 'oftalmologia']],
                         [request['canonical'] for request in requests])

    def test_ambiguous_multi_request_negation_suspends_all_requests(self):
        self.ingest(self.extended(('user', 'Quero ginecologista e oftalmologista'),
                                 ('user', 'Não quero esse')))
        self.assertFalse(self.state().specialty_term_hmacs)
        self.assertEqual('especialidade', self.state().phase)
        self.assertIsNotNone(self.state().cpf_hmac)
        self.assertTrue(self.state().city_term_hmacs)

    def test_negative_readback_removes_only_the_named_specialty(self):
        self.ingest(self.extended(('user', 'Quero ginecologista e oftalmologista'),
                                 ('bot', 'Você quer cardiologista, certo?'), ('user', 'Não')))
        for query in ['Ginecologia', 'Oftalmologia']: self.validate(query=query)
        with self.assertRaises(BusinessRuleError): self.validate(query='Cardiologia')

    def test_refresh_generation_tracks_explicit_user_turn_and_is_replay_stable(self):
        self.ingest(self.standard())
        self.assertIsNone(self.state().conversation_meta.get('refresh_turn'))
        ms = self.extended(('user', 'Consulte novamente'))
        self.ingest(ms, rev=2)
        first = self.state().conversation_meta['refresh_turn']
        self.assertEqual(self.state().conversation_meta['last_user'], first)
        self.assertEqual(2, self.state().conversation_meta['schema_version'])
        self.validate()
        self.ingest(ms, rev=3)
        self.assertEqual(first, self.state().conversation_meta['refresh_turn'])
        ms.append({'role': 'user', 'message': 'Cardiologista', 'time': self.base+7000})
        self.ingest(ms, rev=4)
        self.assertEqual(first, self.state().conversation_meta['refresh_turn'])
        for index, text in enumerate(['Atualize a busca', 'Pesquise de novo'], 8):
            ms.append({'role': 'user', 'message': text, 'time': self.base+index*1000})
            self.ingest(ms, rev=index)
            new = self.state().conversation_meta['refresh_turn']
            self.assertNotEqual(first, new)
            first = new

    def test_negated_refresh_does_not_request_new_search(self):
        self.ingest(self.extended(('user', 'Não consulte novamente')))
        self.assertIsNone(self.state().conversation_meta.get('refresh_turn'))
        self.validate()

    def test_negative_hearing_answer_does_not_revoke_specialty(self):
        self.ingest(self.extended(('bot', 'Está me ouvindo?'), ('user', 'Não')))
        self.validate()

    def test_unknown_specialty_corrected_by_readback_replaces_prior_value(self):
        ms = self.standard()
        ms[5]['message'] = 'Uroista'
        ms.extend([{'role': 'bot', 'message': 'Você quis dizer urologista, certo?', 'time': self.base+6000},
                   {'role': 'user', 'message': 'Sim', 'time': self.base+7000}])
        self.ingest(ms)
        self.validate(query='Urologia')
        with self.assertRaises(BusinessRuleError): self.validate(query='Uroista')

    def test_schema_one_ledger_preserves_evidence_on_incremental_update(self):
        self.ingest(self.standard())
        with self.sessions() as session:
            state = session.get(VapiCallSlotState, {'tenant_id': 'tenant_a', 'call_id': 'same-call'})
            meta = copy.deepcopy(state.conversation_meta)
            meta.pop('schema_version', None)
            meta.pop('active_requests', None)
            for entry in meta['turns'].values():
                entry.pop('requests', None)
                entry.pop('removed_requests', None)
            state.conversation_meta = meta
            session.commit()
        self.ingest([{'role': 'user', 'message': 'Consulte novamente', 'time': self.base+6000}], rev=2)
        self.validate()

    def test_multi_request_negative_confirmation_suspends_ambiguous_set_once(self):
        ms = self.extended(('user', 'Quero ginecologista e oftalmologista'),
                           ('bot', 'Você quer cardiologista ou oftalmologista, certo?'), ('user', 'Não'))
        self.ingest(ms)
        self.assertFalse(self.state().specialty_term_hmacs)
        self.ingest(ms, rev=2)
        self.assertEqual(1, self.state().conversation_meta['failures']['especialidade'])

    def test_city_confirmation_does_not_accept_unspoken_cross_slot_terms(self):
        self.ingest(self.extended(('bot', 'A cidade é Camaçari, certo?'), ('user', 'Sim')))
        self.validate(city='Camaçari')
        with self.assertRaises(BusinessRuleError): self.validate(city='certo')
        with self.assertRaises(BusinessRuleError): self.validate(city='Camaçari', query='Camaçari')

    def test_explicit_swap_keeps_unrelated_active_request(self):
        self.ingest(self.extended(('user', 'Quero ginecologista'),
                                 ('user', 'Troque cardiologista por urologista')))
        self.validate(query='Ginecologia')
        self.validate(query='Urologia')
        with self.assertRaises(BusinessRuleError): self.validate(query='Cardiologia')

    def test_negative_identity_then_explicit_replacement_removes_old(self):
        self.ingest(self.extended(('user', 'Não é cardiologista, quero urologista')))
        self.validate(query='Urologia')
        with self.assertRaises(BusinessRuleError): self.validate(query='Cardiologia')

    def test_negative_named_city_revokes_city_and_preserves_requests(self):
        self.ingest(self.extended(('user', 'Não é Salvador')))
        self.assertFalse(self.state().city_term_hmacs)
        self.assertTrue(self.state().specialty_term_hmacs)
        self.assertIsNotNone(self.state().cpf_hmac)
        self.assertEqual('cidade', self.state().phase)

    def test_mixed_city_and_specialty_negation_requires_city_clarification(self):
        self.ingest(self.extended(('user',
            'Não quero cardiologista em Salvador, quero urologista em Camaçari')))
        with self.assertRaises(BusinessRuleError) as error:
            self.validate(query='Urologia')
        self.assertEqual('cidade', error.exception.field)
        self.assertFalse(self.state().city_term_hmacs)
        self.assertIsNotNone(self.state().cpf_hmac)
        # Clarifying the location must retain the independently requested swap.
        messages = self.extended(('user',
            'Não quero cardiologista em Salvador, quero urologista em Camaçari'),
            ('bot', 'Qual cidade?'), ('user', 'Camaçari'))
        self.ingest(messages, rev=2)
        self.validate(city='Camaçari', query='Urologia')
        with self.assertRaises(BusinessRuleError):
            self.validate(city='Camaçari', query='Cardiologia')

    def test_specialty_negation_does_not_negate_later_positive_city(self):
        self.ingest(self.extended(('user',
            'Não quero cardiologista, quero urologista em Camaçari')))
        self.validate(city='Camaçari', query='Urologia')
        with self.assertRaises(BusinessRuleError):
            self.validate(query='Urologia')

    def test_ambiguous_negative_city_answer_revokes_pending_city_only(self):
        self.ingest(self.extended(('bot', 'Qual cidade?'), ('user', 'Não é essa')))
        self.assertFalse(self.state().city_term_hmacs)
        self.assertTrue(self.state().specialty_term_hmacs)

    def test_explicit_city_confirmation_without_certo_accepts_corrected_value(self):
        self.ingest(self.extended(('bot', 'Só para confirmar: a cidade é Camaçari?'), ('user', 'Sim')))
        self.validate(city='Camaçari')
        with self.assertRaises(BusinessRuleError): self.validate(city='Salvador')

    def test_open_city_confirmation_question_does_not_invent_city(self):
        self.ingest(self.extended(('bot', 'Qual cidade você quer confirmar?'), ('user', 'Sim')))
        self.validate()
        with self.assertRaises(BusinessRuleError): self.validate(city='você quer confirmar')

    async def test_new_tool_ids_reuse_canonical_query_and_ignore_legacy_neighborhood(self):
        first = (await self.dispatch(self.standard(), [self.tool()]))['results'][0]['result']
        tool = self.tool(id='new-tool', query='cardiologista')
        tool['function']['arguments']['neighborhood'] = 'Centro'
        second = (await self.dispatch(self.standard(), [tool]))['results'][0]['result']
        self.assertTrue(first['ok'])
        self.assertTrue(second['ok'])
        self.assertTrue(second['data']['reused_result'])
        self.provider.search_providers.assert_called_once()

    async def test_cached_result_does_not_bypass_negative_confirmation(self):
        await self.dispatch(self.standard(), [self.tool()])
        messages = self.extended(('bot', 'A cidade é Salvador, certo?'), ('user', 'Não'))
        result = (await self.dispatch(messages, [self.tool(id='invalidated')], rev=2))['results'][0]['result']
        self.assertFalse(result['ok'])
        self.assertEqual('SLOT_UNCONFIRMED', result['data']['upstream_code'])
        self.provider.search_providers.assert_called_once()

    async def test_explicit_refresh_runs_once_but_repeated_request_reuses(self):
        await self.dispatch(self.standard(), [self.tool()])
        messages = self.extended(('user', 'Consulte novamente'))
        refreshed = (await self.dispatch(messages, [self.tool(id='refresh')], rev=2))['results'][0]['result']
        repeated = (await self.dispatch(messages, [self.tool(id='refresh-repeat')], rev=3))['results'][0]['result']
        self.assertTrue(refreshed['ok'])
        self.assertTrue(repeated['data']['reused_result'])
        self.assertEqual(2, self.provider.search_providers.call_count)

    async def test_service_type_change_is_a_new_query(self):
        await self.dispatch(self.standard(), [self.tool()])
        tool = self.tool(id='changed-type')
        tool['function']['arguments']['tipo_atendimento'] = 'online'
        result = (await self.dispatch(self.standard(), [tool]))['results'][0]['result']
        self.assertTrue(result['ok'])
        self.assertEqual(2, self.provider.search_providers.call_count)

    async def test_late_business_error_does_not_reopen_terminal_state_after_completion(self):
        from app.tenants.pbsaude.search_execution import execute_search
        from app.tenants.pbsaude.workflows.search_providers import search_providers
        self.ingest(self.standard())
        self.provider.search_providers.side_effect = BusinessRuleError(
            code='CIDADE_INVALIDA', field='cidade', message='Cidade invalida')
        def finish_then_close(**kwargs):
            try:
                return execute_search(**kwargs)
            except BusinessRuleError:
                # Deterministically interleave a terminal event after the worker's
                # completion transaction but before its async caller receives it.
                with self.sessions() as session:
                    state = session.get(VapiCallSlotState, ('tenant_a', 'same-call'))
                    state.conversation_meta = {**state.conversation_meta, 'terminal': True,
                                               'recovery_attempts': {}, 'recovery_field': None}
                    state.phase = 'closed'
                    session.commit()
                raise
        with patch('app.tenants.pbsaude.workflows.search_providers.execute_search', side_effect=finish_then_close):
            with self.assertRaises(BusinessRuleError):
                await search_providers(self.tool()['function']['arguments'], self.settings, 'same-call', 'tenant_a')
        state = self.state()
        self.assertEqual('closed', state.phase)
        self.assertFalse(state.conversation_meta['recovery_attempts'])
        self.assertIsNone(state.conversation_meta['recovery_field'])

    def test_recovery_gate_requires_new_field_evidence_before_catalog_or_provider(self):
        self.settings.pbsaude_vapi_recovery_gate_enabled = True
        messages = self.standard()
        messages[-1]['message'] = 'Exame de vista'
        self.ingest(messages)
        with self.assertRaises(BusinessRuleError) as rejected:
            self.direct_search(query='Exame de vista')
        self.assertEqual('ESPECIALIDADE_INVALIDA', rejected.exception.code)

        state = self.state()
        meta = state.conversation_meta
        self.assertEqual('especialidade', meta['recovery_field'])
        self.assertEqual(meta['last_user'], meta['recovery_anchor_user'])
        self.assertEqual('ESPECIALIDADE_INVALIDA', meta['recovery_code'])
        self.assertEqual(64, len(meta['rejected_attempt_hmac']))
        self.assertNotIn('Exame de vista', json.dumps(meta))

        with (
            patch('app.tenants.pbsaude.workflows.search_providers.get_specialty_catalog',
                  side_effect=AssertionError('catalog accessed while recovery is pinned')),
            patch('app.tenants.pbsaude.workflows.search_providers.get_data_provider',
                  side_effect=AssertionError('provider accessed while recovery is pinned')),
        ):
            with self.assertRaises(BusinessRuleError) as blocked:
                self.direct_search(query='Exame de vista')
        self.assertEqual('USER_TURN_REQUIRED', blocked.exception.code)
        self.assertEqual('collect_especialidade', blocked.exception.details['recovery_action'])
        self.assertEqual(0, blocked.exception.attempt)
        self.provider.search_providers.assert_not_called()

    def test_missing_recoverable_argument_pins_backend_field(self):
        self.settings.pbsaude_vapi_recovery_gate_enabled = True
        self.ingest(self.standard())
        from app.tenants.pbsaude.workflows.search_providers import _search_providers
        with self.assertRaises(BusinessRuleError) as error:
            _search_providers(
                {'cpf': CPF, 'city': 'Salvador'},
                self.settings,
                'same-call',
                'tenant_a',
            )
        self.assertEqual('ESPECIALIDADE_INVALIDA', error.exception.code)
        self.assertEqual('especialidade', self.state().conversation_meta['recovery_field'])
        self.provider.search_providers.assert_not_called()

    def test_recovery_attempts_count_distinct_eligible_user_turns(self):
        self.settings.pbsaude_vapi_recovery_gate_enabled = True
        messages = self.standard()
        messages[-1]['message'] = 'Exame de vista'
        self.ingest(messages)
        with self.assertRaises(BusinessRuleError) as first:
            self.direct_search(query='Exame de vista')
        self.assertEqual(1, first.exception.attempt)

        messages.extend([
            {'role': 'bot', 'message': 'Qual especialidade?', 'time': self.base + 6000},
            {'role': 'user', 'message': 'Exame de vista', 'time': self.base + 7000},
        ])
        self.ingest(messages, rev=2)
        with self.assertRaises(BusinessRuleError) as second:
            self.direct_search(query='Exame de vista')
        self.assertEqual(2, second.exception.attempt)
        with self.assertRaises(BusinessRuleError) as replay:
            self.direct_search(query='Exame de vista')
        self.assertEqual('USER_TURN_REQUIRED', replay.exception.code)
        self.assertEqual(0, replay.exception.attempt)

    def test_recovery_gate_ignores_noise_agent_silence_and_incidental_dtmf(self):
        self.settings.pbsaude_vapi_recovery_gate_enabled = True
        messages = self.standard()
        self.ingest(messages)
        with self.assertRaises(BusinessRuleError) as first:
            self.direct_search(city='Manaus')
        self.assertEqual('SLOT_UNCONFIRMED', first.exception.code)

        additions = (
            ('user', 'Alô?'),
            ('bot', 'Só um momento.'),
            ('user', ''),
            ('user', "User's Keypad Entry: 7#"),
            ('user', 'Oi'),
        )
        for index, (role, text) in enumerate(additions, 1):
            messages.append({'role': role, 'message': text, 'time': self.base + (6 + index) * 1000})
            self.ingest(messages, rev=index + 1)
            with self.assertRaises(BusinessRuleError) as result:
                self.direct_search(city='Salvador')
            self.assertEqual('USER_TURN_REQUIRED', result.exception.code)
            self.assertEqual(0, result.exception.attempt)
        self.provider.search_providers.assert_not_called()

    def test_recovery_binds_free_speech_and_confirmation_to_pinned_field(self):
        self.settings.pbsaude_vapi_recovery_gate_enabled = True
        messages = self.standard()
        messages[-1]['message'] = 'Exame de vista'
        self.ingest(messages)
        with self.assertRaises(BusinessRuleError):
            self.direct_search(query='Exame de vista')

        messages.extend([
            {'role': 'bot', 'message': 'A cidade é Camaçari, certo?', 'time': self.base + 6000},
            {'role': 'user', 'message': 'Sim', 'time': self.base + 7000},
        ])
        self.ingest(messages, rev=2)
        with self.assertRaises(BusinessRuleError) as wrong_confirmation:
            self.direct_search(city='Salvador', query='Urologia')
        self.assertEqual('USER_TURN_REQUIRED', wrong_confirmation.exception.code)
        self.assertEqual('especialidade', self.state().conversation_meta['recovery_field'])

        messages.append({
            'role': 'user',
            'message': 'Corrigindo a cidade: Camaçari',
            'time': self.base + 8000,
        })
        self.ingest(messages, rev=3)
        with self.assertRaises(BusinessRuleError) as other_field_correction:
            self.direct_search(city='Camaçari', query='Urologia')
        self.assertEqual('USER_TURN_REQUIRED', other_field_correction.exception.code)
        self.assertEqual('especialidade', self.state().conversation_meta['recovery_field'])

        messages.extend([
            {'role': 'bot', 'message': 'Você quis dizer urologista, certo?', 'time': self.base + 9000},
            {'role': 'user', 'message': 'Sim', 'time': self.base + 10000},
        ])
        self.ingest(messages, rev=4)
        confirmed = self.direct_search(city='Camaçari', query='Urologia')
        self.assertEqual([], confirmed[0]['providers'])
        self.assertNotIn('recovery_field', self.state().conversation_meta)
        self.provider.search_providers.assert_called_once()

        # A fresh recovery accepts ordinary speech as the backend-pinned city,
        # even if the model asks an unrelated question in between.
        self.provider.search_providers.reset_mock()
        self.provider.search_providers.side_effect = BusinessRuleError(
            code='CIDADE_INVALIDA', field='cidade', message='Cidade invalida')
        messages.extend([
            {'role': 'user', 'message': 'Consulte novamente', 'time': self.base + 11000},
        ])
        self.ingest(messages, rev=5)
        with self.assertRaises(BusinessRuleError) as failed:
            self.direct_search(city='Camaçari', query='Urologia')
        self.assertEqual('CIDADE_INVALIDA', failed.exception.code)
        self.provider.search_providers.side_effect = None
        messages.extend([
            {'role': 'bot', 'message': 'Qual especialidade?', 'time': self.base + 12000},
            {'role': 'user', 'message': 'Salvador', 'time': self.base + 13000},
        ])
        self.ingest(messages, rev=6)
        recovered = self.direct_search(city='Salvador', query='Urologia')
        self.assertEqual([], recovered[0]['providers'])

    def test_provider_search_events_are_persisted_without_plaintext_inputs(self):
        self.settings.pbsaude_vapi_recovery_gate_enabled = True
        self.ingest(self.standard())
        self.direct_search()
        self.direct_search()

        messages = self.extended(('user', 'Consulte novamente'))
        self.ingest(messages, rev=3)
        self.provider.search_providers.side_effect = TimeoutError('secret technical detail')
        with self.assertRaises(TimeoutError):
            self.direct_search()
        self.provider.search_providers.side_effect = None
        with self.assertRaises(BusinessRuleError):
            self.direct_search(city='Manaus')
        with self.assertRaises(BusinessRuleError) as blocked:
            self.direct_search(city='Salvador')
        self.assertEqual('USER_TURN_REQUIRED', blocked.exception.code)

        with self.sessions() as session:
            events = session.scalars(
                select(CallEvent).where(CallEvent.tool_name == 'search_providers')
            ).all()
        event_types = {event.event_type for event in events}
        self.assertTrue({
            'provider_search_requested',
            'provider_search_blocked',
            'provider_search_upstream_started',
            'provider_search_completed',
            'provider_search_result_reused',
            'provider_search_failed',
            'provider_handoff_recommended',
        }.issubset(event_types))
        serialized = json.dumps([event.payload_masked for event in events])
        for plaintext in (CPF, 'Salvador', 'Cardiologia', 'secret technical detail'):
            self.assertNotIn(plaintext, serialized)

    async def test_recovery_gate_opt_out_keeps_legacy_turn_counting(self):
        self.ingest(self.standard())
        with patch(
            'app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread',
            new=AsyncMock(side_effect=lambda function, *args: function(*args)),
        ), patch(
            'app.tenants.pbsaude.workflows.search_providers._search_providers',
            side_effect=BusinessRuleError(
                code='CIDADE_INVALIDA', field='cidade', message='Cidade invalida'),
        ):
            first = (await self.dispatch(self.standard(), [self.tool('legacy-first')]))['results'][0]['result']
            second = (await self.dispatch(self.standard(), [self.tool('legacy-second')]))['results'][0]['result']

        self.assertEqual('CIDADE_INVALIDA', first['data']['upstream_code'])
        self.assertEqual(1, first['data']['attempt'])
        self.assertEqual(1, second['data']['attempt'])
        self.assertNotIn('recovery_anchor_user', self.state().conversation_meta)

    def test_search_lifecycle_events_emit_without_slot_guard_or_duplication(self):
        self.settings.vapi_slot_guard_enabled = False
        self.direct_search()
        with self.sessions() as session:
            unguarded_events = session.scalars(
                select(CallEvent).where(CallEvent.tool_name == 'search_providers')
            ).all()
        self.assertEqual(
            ['provider_search_requested', 'provider_search_upstream_started', 'provider_search_completed'],
            [event.event_type for event in unguarded_events],
        )

        self.settings.vapi_slot_guard_enabled = True
        self.ingest(self.standard(), rev=2)
        self.direct_search()
        with self.sessions() as session:
            guarded_events = session.scalars(
                select(CallEvent).where(CallEvent.tool_name == 'search_providers')
            ).all()
        self.assertEqual(2, sum(event.event_type == 'provider_search_upstream_started' for event in guarded_events))
        self.assertEqual(2, sum(event.event_type == 'provider_search_completed' for event in guarded_events))

    async def test_async_dispatcher_blocks_recovery_replay_without_new_user_turn(self):
        self.settings.pbsaude_vapi_recovery_gate_enabled = True
        messages = self.standard()
        messages[-1]['message'] = 'Exame de vista'
        with patch(
            'app.tenants.pbsaude.workflows.search_providers.asyncio.to_thread',
            new=AsyncMock(side_effect=lambda function, *args: function(*args)),
        ):
            first = (await self.dispatch(messages, [self.tool('recovery-first', query='Exame de vista')]))['results'][0]['result']
            replay = (await self.dispatch(messages, [self.tool('recovery-replay', query='Exame de vista')]))['results'][0]['result']

        self.assertEqual('ESPECIALIDADE_INVALIDA', first['data']['upstream_code'])
        self.assertFalse(replay['ok'])
        self.assertEqual('USER_TURN_REQUIRED', replay['data']['upstream_code'])
        self.assertEqual(0, replay['data']['attempt'])
        self.assertEqual('collect_especialidade', replay['data']['recovery_action'])
        self.assertEqual('EM_ANDAMENTO', replay['final_state'])
        self.provider.search_providers.assert_not_called()

    def test_search_event_persistence_failure_logs_safe_operational_signal(self):
        from app.tenants.pbsaude.search_events import persist_search_event

        with (
            patch('app.tenants.pbsaude.search_events.slot_guard.SessionLocal', side_effect=RuntimeError('db unavailable')),
            patch('app.tenants.pbsaude.search_events.log') as log,
        ):
            persist_search_event(
                settings=self.settings,
                tenant_id='tenant_a',
                call_id='same-call',
                event_type='provider_search_requested',
            )

        log.warning.assert_called_once_with(
            'provider_search_event_persistence_failed',
            tenant_id='tenant_a',
            call_id='same-call',
            event_type='provider_search_requested',
        )
