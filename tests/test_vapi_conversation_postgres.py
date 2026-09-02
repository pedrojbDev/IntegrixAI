"""Run against a disposable migrated database with VAPI_TEST_DATABASE_URL."""
import copy
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.tools.registry import TenantToolRegistry
from app.models.vapi_call_slot_state import VapiCallSlotState
from app.models.vapi_webhook_receipt import VapiWebhookReceipt
from app.platform.services.vapi_event_ingestion import VapiEventIngestionService
from app.platform.services.vapi_conversation import keyed_hmac
from app.tenants.pbsaude.conversation import capture_pbsaude_conversation
from app.tenants.pbsaude.tool_handlers import register_pbsaude_handlers


@unittest.skipUnless(os.environ.get("VAPI_TEST_DATABASE_URL"), "disposable PostgreSQL not configured")
class ConversationPostgresTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ["VAPI_TEST_DATABASE_URL"])
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(bind=self.engine)
        self.call_id = "test-" + uuid.uuid4().hex
        self.settings = Settings(_env_file=None, db_enabled=True,
            tenant_map={"+551100000001": "tenant_a", "+551100000002": "tenant_b"},
            vapi_slot_guard_enabled=True, vapi_slot_state_hmac_secret="test-evidence-key")
        register_pbsaude_handlers(TenantToolRegistry())
        self.now = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.payload = {"message": {"type": "conversation-update", "timestamp": self.now,
            "call": {"id": self.call_id, "to": "+551100000001"},
            "messages": [{"role": role, "message": text, "time": self.now - 10000 + i * 1000}
                for i, (role, text) in enumerate([
                    ("user", "User's Keypad Entry: 12345678901#"),
                    ("bot", "Qual cidade?"), ("user", "Salvador"),
                    ("bot", "Qual especialidade?"), ("user", "Cardiologista")])]}}

    def test_concurrent_duplicate_receipts_and_absent_state_creation(self):
        barrier = Barrier(6)
        def ingest(_):
            barrier.wait(timeout=10)
            with self.sessions() as session:
                return VapiEventIngestionService(self.settings).ingest(session, self.payload)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(ingest, range(6)))
        self.assertEqual(1, sum(not r.duplicate for r in results))
        with self.sessions() as session:
            self.assertEqual(1, session.scalar(select(func.count()).select_from(VapiWebhookReceipt)
                .where(VapiWebhookReceipt.provider_call_id == self.call_id)))

    def test_tools_and_events_converge_on_latest_revision_with_tenant_isolation(self):
        barrier = Barrier(6)
        def ingest(index):
            payload = copy.deepcopy(self.payload)
            payload['message']['timestamp'] += index
            payload['message']['messages'][2]['message'] = 'Feira de Santana' if index == 5 else 'Salvador'
            barrier.wait(timeout=10)
            with self.sessions() as session:
                if index % 2:
                    capture_pbsaude_conversation(session, self.settings, 'tenant_a', self.call_id, payload['message'])
                    session.commit()
                else:
                    VapiEventIngestionService(self.settings).ingest(session, payload)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(ingest, range(6)))
        other = copy.deepcopy(self.payload)
        other['message']['call']['to'] = '+551100000002'
        with self.sessions() as session:
            VapiEventIngestionService(self.settings).ingest(session, other)
            a = session.get(VapiCallSlotState, {'tenant_id': 'tenant_a', 'call_id': self.call_id})
            b = session.get(VapiCallSlotState, {'tenant_id': 'tenant_b', 'call_id': self.call_id})
            city = keyed_hmac(self.settings.vapi_slot_state_hmac_secret, 'feira de santana')
            self.assertIn(city, a.city_term_hmacs)
            self.assertNotIn(city, b.city_term_hmacs)
