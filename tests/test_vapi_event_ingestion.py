import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.ops.cost_sync_service import VapiCostSyncService
from app.core.ops.dashboard_service import get_overview
from app.db import Base
from app.models.call_event import CallEvent
from app.models.vapi_call_slot_state import VapiCallSlotState
from app.models.vapi_webhook_receipt import VapiWebhookReceipt
from app.platform.services.vapi_event_ingestion import VapiEventIngestionService, keyed_hmac
from app.tenants.pbsaude.catalog import get_specialty_catalog
from app.tenants.pbsaude.integration.client import BusinessRuleError
from app.tenants.pbsaude.slot_guard import validate_search_slot_provenance


class VapiEventIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.session_local = sessionmaker(
            bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
        self.settings = Settings(
            _env_file=None,
            db_enabled=True,
            tenant_map={"+5511999999999": "tenant_a", "+5521999999999": "tenant_b"},
            vapi_slot_guard_enabled=True,
            vapi_slot_state_hmac_secret="slot-state-test-secret",
        )

    @staticmethod
    def _conversation(call_id: str, to_number: str, messages: list[str]) -> dict:
        return {
            "message": {
                "type": "conversation-update",
                "call": {"id": call_id, "to": to_number},
                "artifact": {"messages": [{"role": "user", "message": item} for item in messages]},
            }
        }

    def test_captures_hashed_slots_without_persisting_conversation(self) -> None:
        payload = self._conversation(
            "call_1",
            "+5511999999999",
            ["User's Keypad Entry: 12345678901#", "moro em Salvador", "preciso de cardiologista"],
        )
        with self.session_local() as session:
            service = VapiEventIngestionService(self.settings)
            result = service.ingest(session, payload)
            duplicate = service.ingest(session, payload)
            state = session.get(VapiCallSlotState, {"tenant_id": "tenant_a", "call_id": "call_1"})
            receipt = session.scalar(select(VapiWebhookReceipt))

        self.assertTrue(result.accepted)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual("especialidade", state.phase)
        self.assertNotEqual("12345678901", state.cpf_hmac)
        self.assertTrue(state.city_term_hmacs)
        self.assertTrue(state.specialty_term_hmacs)
        self.assertNotIn("Salvador", str(receipt.payload_sanitized))
        self.assertNotIn("cardiologista", str(receipt.payload_sanitized))

    def test_spoken_digits_do_not_confirm_dtmf_cpf(self) -> None:
        payload = self._conversation(
            "call_spoken_cpf",
            "+5511999999999",
            ["meu CPF e 12345678901", "Salvador", "cardiologista"],
        )
        with self.session_local() as session:
            VapiEventIngestionService(self.settings).ingest(session, payload)
            state = session.get(
                VapiCallSlotState,
                {"tenant_id": "tenant_a", "call_id": "call_spoken_cpf"},
            )

        self.assertEqual("cpf", state.phase)
        self.assertIsNone(state.cpf_hmac)

    def test_slot_guard_blocks_invented_city_and_accepts_specialty_alias(self) -> None:
        secret = self.settings.vapi_slot_state_hmac_secret
        now = datetime.now(timezone.utc)
        with self.session_local() as session:
            session.add(
                VapiCallSlotState(
                    tenant_id="tenant_a",
                    call_id="call_1",
                    phase="especialidade",
                    cpf_hmac=keyed_hmac(secret, "12345678901"),
                    city_term_hmacs=[keyed_hmac(secret, "salvador")],
                    specialty_term_hmacs=[keyed_hmac(secret, "cardiologista")],
                    processed_message_hmacs=[],
                    expires_at=now + timedelta(hours=1),
                )
            )
            session.commit()

        catalog = get_specialty_catalog(self.settings)
        with patch("app.tenants.pbsaude.slot_guard.SessionLocal", self.session_local):
            validate_search_slot_provenance(
                settings=self.settings,
                tenant_id="tenant_a",
                call_id="call_1",
                cpf="12345678901",
                city="Salvador",
                query="Cardiologia",
                catalog=catalog,
            )
            with self.assertRaises(BusinessRuleError) as raised:
                validate_search_slot_provenance(
                    settings=self.settings,
                    tenant_id="tenant_a",
                    call_id="call_1",
                    cpf="12345678901",
                    city="Manaus",
                    query="Cardiologia",
                    catalog=catalog,
                )
        self.assertEqual("cidade", raised.exception.field)
        self.assertEqual("collect_cidade", raised.exception.details["recovery_action"])
        with self.session_local() as session:
            state = session.get(VapiCallSlotState, {"tenant_id": "tenant_a", "call_id": "call_1"})
        self.assertEqual("cidade", state.phase)
        self.assertFalse(state.city_term_hmacs)

    def test_native_handoff_is_idempotent_success_and_isolated_by_tenant(self) -> None:
        end_payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "shared_call", "to": "+5511999999999"},
                "endedReason": "assistant-forwarded-call",
            }
        }
        tenant_b_payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "shared_call", "to": "+5521999999999"},
                "endedReason": "assistant-forwarded-call",
            }
        }
        with self.session_local() as session:
            session.add(
                CallEvent(
                    tenant_id="tenant_a",
                    call_id="shared_call",
                    tool_name="search_providers",
                    event_type="tool_completed",
                    final_state="RESOLVIDA_AUTOMATICO",
                    ok=True,
                    duration_ms=200,
                    payload_masked={},
                )
            )
            session.commit()
            service = VapiEventIngestionService(self.settings)
            service.ingest(session, end_payload)
            service.ingest(session, end_payload)
            service.ingest(session, tenant_b_payload)
            events = session.execute(select(CallEvent).order_by(CallEvent.tenant_id)).scalars().all()
            overview = get_overview(session, window="24h", tenant_id="tenant_a", assistant_id=None)
            receipt_count = session.scalar(select(func.count(VapiWebhookReceipt.id)))

        native_events = [event for event in events if event.event_type == "vapi_native_transfer_completed"]
        self.assertEqual(2, len(native_events))
        self.assertEqual({"tenant_a", "tenant_b"}, {event.tenant_id for event in native_events})
        self.assertTrue(native_events[0].ok)
        self.assertEqual(1, overview["kpis"]["successful_handoff_calls"])
        self.assertEqual(1, overview["kpis"]["successful_agent_calls"])
        self.assertEqual(0, overview["kpis"]["automated_resolution_calls"])
        # One raw receipt plus one semantic handoff receipt for each tenant.
        self.assertEqual(4, receipt_count)

    def test_cost_sync_snapshot_redacts_transcript_recording_and_cpf(self) -> None:
        parsed = VapiCostSyncService(self.settings)._parse_call(
            {
                "id": "call_cost",
                "to": "+5511999999999",
                "artifact": {"transcript": "private conversation", "recordingUrl": "https://private"},
                "cpf": "12345678901",
            }
        )
        self.assertIsNotNone(parsed)
        snapshot = str(parsed.raw_call_json)
        self.assertNotIn("private conversation", snapshot)
        self.assertNotIn("12345678901", snapshot)
        self.assertNotIn("recordingUrl", snapshot)
