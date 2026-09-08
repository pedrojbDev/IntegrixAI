"""Run only against a disposable migrated VAPI_TEST_DATABASE_URL database."""
import asyncio
import multiprocessing
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.models.vapi_search_execution import VapiSearchExecution
from app.tenants.pbsaude.integration.client import BusinessRuleError
from app.tenants.pbsaude.search_execution import execute_search
from app.tenants.pbsaude.workflows.search_providers import search_providers
import test_vapi_search_execution as shared


def process_search(url, call_id, ready, release):
    engine = create_engine(url)
    sessions = sessionmaker(engine)
    settings = Settings(_env_file=None, db_enabled=True, vapi_slot_guard_enabled=True,
                        vapi_slot_state_hmac_secret='execution-test')
    def upstream():
        ready.set()
        if not release.wait(10):
            raise RuntimeError('test barrier timed out')
        return {'providers': []}, 'RESOLVIDA_AUTOMATICO'
    try:
        with patch('app.tenants.pbsaude.slot_guard.SessionLocal', sessions):
            execute_search(settings=settings, tenant_id='a', call_id=call_id,
                           signature='query', validate=lambda session: None, execute=upstream)
    finally:
        engine.dispose()


@unittest.skipUnless(os.environ.get('VAPI_TEST_DATABASE_URL'), 'disposable PostgreSQL not configured')
class SearchPostgresTests(shared.SearchExecutionTests):
    def setUp(self):
        self.engine = create_engine(os.environ['VAPI_TEST_DATABASE_URL'])
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(self.engine)
        self.patch = patch('app.tenants.pbsaude.slot_guard.SessionLocal', self.sessions)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.settings = Settings(_env_file=None, db_enabled=True, vapi_slot_guard_enabled=True,
                                 vapi_slot_state_hmac_secret='execution-test')
        self.call_id = 'test-' + uuid.uuid4().hex
        self.seed('a')

    def test_separate_process_holds_call_lock(self):
        context = multiprocessing.get_context('spawn')
        ready, release = context.Event(), context.Event()
        process = context.Process(target=process_search,
            args=(os.environ['VAPI_TEST_DATABASE_URL'], self.call_id, ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(10))
            with self.assertRaises(BusinessRuleError) as error:
                self.run_search(lambda: self.fail('second process entered upstream'), signature='other-query')
            self.assertEqual('wait_current_search', error.exception.details['recovery_action'])
            # A different tenant is independent even when call ids match.
            self.seed('b')
            self.run_search(lambda: ({'providers': []}, 'RESOLVIDA_AUTOMATICO'), tenant='b')
        finally:
            release.set()
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)
        self.assertEqual(0, process.exitcode)
        self.assertTrue(self.run_search(lambda: self.fail('completed result not reused'))[0]['reused_result'])

    def test_crashed_worker_does_not_trigger_automatic_retry(self):
        context = multiprocessing.get_context('spawn')
        ready, release = context.Event(), context.Event()
        process = context.Process(target=process_search,
            args=(os.environ['VAPI_TEST_DATABASE_URL'], self.call_id, ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(10))
        finally:
            process.terminate()
            process.join(5)
        with self.assertRaises(BusinessRuleError) as error:
            self.run_search(lambda: self.fail('retried crashed upstream'))
        self.assertEqual('offer_handoff', error.exception.details['recovery_action'])

    def test_timeout_and_cancellation_keep_lock_until_real_worker_ends(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                self.call_id = 'test-' + uuid.uuid4().hex
                self.seed('a')
                entered, release, finished = Event(), Event(), Event()
                provider = Mock()
                def slow(*args):
                    entered.set()
                    if not release.wait(5):
                        raise RuntimeError('test barrier timed out')
                    return []
                provider.search_providers.side_effect = slow
                self.settings.provider_timeout_seconds = 0.1
                from app.tenants.pbsaude import search_execution
                real_execute = search_execution.execute_search
                def tracked(**kwargs):
                    try:
                        return real_execute(**kwargs)
                    finally:
                        finished.set()
                async def scenario():
                    with patch('app.tenants.pbsaude.workflows.search_providers.get_data_provider', return_value=provider), \
                         patch('app.tenants.pbsaude.workflows.search_providers.validate_search_slot_provenance'), \
                         patch('app.tenants.pbsaude.workflows.search_providers.clear_recovery_attempts'), \
                         patch('app.tenants.pbsaude.workflows.search_providers.execute_search', side_effect=tracked):
                        task = asyncio.create_task(search_providers({'cpf': '12345678901',
                            'city': 'Salvador', 'query': 'Cardiologia'}, self.settings, self.call_id, 'a'))
                        try:
                            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                            if cancel:
                                task.cancel()
                            with self.assertRaises(asyncio.CancelledError if cancel else TimeoutError):
                                await task
                            with self.assertRaises(BusinessRuleError) as error:
                                await asyncio.to_thread(self.run_search, lambda: self.fail('early unlock'))
                            self.assertEqual('wait_current_search', error.exception.details['recovery_action'])
                        finally:
                            release.set()
                            self.assertTrue(await asyncio.to_thread(finished.wait, 5))
                        provider.search_providers.assert_called_once()
                asyncio.run(scenario())

    def test_one_connection_pool_can_finish_and_reuse_search(self):
        self.engine.dispose()
        self.engine = create_engine(os.environ['VAPI_TEST_DATABASE_URL'], pool_size=1,
                                    max_overflow=0, pool_timeout=0.2)
        self.addCleanup(self.engine.dispose)
        sessions = sessionmaker(self.engine)
        with patch('app.tenants.pbsaude.slot_guard.SessionLocal', sessions):
            self.run_search(lambda: ({'providers': []}, 'RESOLVIDA_AUTOMATICO'))
            self.assertTrue(self.run_search(lambda: self.fail('cache miss'))[0]['reused_result'])

    def test_state_lock_covers_validation_cache_and_completion_but_not_http(self):
        import hashlib
        from sqlalchemy import text
        key = int.from_bytes(hashlib.sha256(f'vapi-state:a:{self.call_id}'.encode()).digest()[:8],
                             'big', signed=True)
        validations = []
        def state_lock_available():
            with self.engine.connect() as probe:
                return probe.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': key})
        def validate(session):
            validations.append(session.connection())
            self.assertFalse(state_lock_available())
        def execute():
            self.assertTrue(state_lock_available())
            self.assertFalse(validations[-1].in_transaction())
            return {'providers': []}, 'RESOLVIDA_AUTOMATICO'
        def complete(session):
            self.assertFalse(state_lock_available())
        kwargs = dict(settings=self.settings, tenant_id='a', call_id=self.call_id,
                      signature='query', validate=validate, execute=execute, complete=complete)
        execute_search(**kwargs)
        self.assertTrue(execute_search(**kwargs)[0]['reused_result'])
        self.assertEqual(3, len(validations))
