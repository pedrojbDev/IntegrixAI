import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import Base
from app.models.vapi_call_slot_state import VapiCallSlotState
from app.tenants.pbsaude.integration.client import BusinessRuleError
from app.tenants.pbsaude.search_execution import execute_search


class SearchExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = create_engine('sqlite:///' + self.tmp.name + '/test.db')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine)
        self.patch = patch('app.tenants.pbsaude.slot_guard.SessionLocal', self.sessions)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.settings = Settings(_env_file=None, db_enabled=True, vapi_slot_guard_enabled=True,
                                 vapi_slot_state_hmac_secret='execution-test')
        self.call_id = 'call'
        self.seed('a')

    def seed(self, tenant):
        with self.sessions() as session:
            session.add(VapiCallSlotState(tenant_id=tenant, call_id=self.call_id, phase='ready',
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                conversation_meta={'field_turns': {'cpf': 'c', 'cidade': 'd', 'especialidade': 'e'}}))
            session.commit()

    def run_search(self, callback, tenant='a', signature='query'):
        return execute_search(settings=self.settings, tenant_id=tenant, call_id=self.call_id,
                              signature=signature, validate=lambda session: None, execute=callback)

    def test_empty_success_reused_and_tenant_isolated(self):
        calls = []
        def search():
            calls.append(True)
            return {'providers': []}, 'RESOLVIDA_AUTOMATICO'
        self.assertNotIn('reused_result', self.run_search(search)[0])
        self.assertTrue(self.run_search(search)[0]['reused_result'])
        self.seed('b')
        self.run_search(search, tenant='b')
        self.assertEqual(2, len(calls))

    def test_concurrent_request_waits_and_refresh_is_stable(self):
        entered, release = Event(), Event()
        def slow():
            entered.set()
            self.assertTrue(release.wait(5))
            return {'providers': []}, 'RESOLVIDA_AUTOMATICO'
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.run_search, slow)
            self.assertTrue(entered.wait(5))
            try:
                with self.assertRaises(BusinessRuleError) as error:
                    self.run_search(lambda: self.fail('duplicate upstream'))
                self.assertEqual('wait_current_search', error.exception.details['recovery_action'])
                self.assertEqual(0, error.exception.attempt)
            finally:
                release.set()
            future.result(5)
        with self.sessions() as session:
            state = session.get(VapiCallSlotState, ('a', self.call_id))
            state.conversation_meta = {**state.conversation_meta, 'refresh_turn': 'refresh-hash'}
            session.commit()
        self.assertNotIn('reused_result', self.run_search(lambda: ({'providers': []}, 'RESOLVIDA_AUTOMATICO'))[0])
        self.assertTrue(self.run_search(lambda: self.fail('duplicate refresh'))[0]['reused_result'])

    def test_failed_execution_not_retried_without_new_input(self):
        def fail():
            raise TimeoutError('upstream')
        with self.assertRaises(TimeoutError):
            self.run_search(fail)
        with self.assertRaises(BusinessRuleError) as error:
            self.run_search(lambda: self.fail('automatic retry'))
        self.assertEqual('offer_handoff', error.exception.details['recovery_action'])
        self.assertFalse(error.exception.retryable)
        self.run_search(lambda: ({'providers': []}, 'RESOLVIDA_AUTOMATICO'), signature='changed')

    def test_result_discarded_after_correction_or_terminal(self):
        for metadata in ({'field_turns': {'cidade': 'new'}}, {'terminal': True}):
            with self.subTest(metadata=metadata):
                def change():
                    with self.sessions() as session:
                        state = session.get(VapiCallSlotState, ('a', self.call_id))
                        state.conversation_meta = metadata
                        session.commit()
                    return {'providers': []}, 'RESOLVIDA_AUTOMATICO'
                with self.assertRaises(BusinessRuleError):
                    self.run_search(change, signature=str(metadata))
