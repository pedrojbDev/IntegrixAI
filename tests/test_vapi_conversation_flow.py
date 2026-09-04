import copy
import json
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.tools.dispatcher import ToolDispatcher
from app.core.tools.registry import TenantToolRegistry
from app.db import Base
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
