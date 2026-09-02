import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.api.routes.vapi_events import ingest_vapi_event
from app.config import Settings
from app.db import Base
from app.models.call_event import CallEvent
from app.models.vapi_webhook_receipt import VapiWebhookReceipt
from app.schemas.vapi_events import VapiServerEvent


class VapiEventsRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        self.settings = Settings(
            _env_file=None,
            db_enabled=True,
            webhook_secret="secret",
            tenant_map={"+5511999999999": "tenant_a"},
        )
    @staticmethod
    def _request(headers: dict[str, str] | None = None) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/vapi/events",
                "headers": [
                    (key.lower().encode("latin-1"), value.encode("latin-1"))
                    for key, value in (headers or {}).items()
                ],
            }
        )

    async def test_rejects_unauthorized_webhook(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await ingest_vapi_event(
                self._request(),
                VapiServerEvent(message={"type": "status-update", "call": {"id": "call_1"}}),
                self.settings,
            )
        self.assertEqual(401, raised.exception.status_code)

    async def test_records_native_handoff_without_transcript(self) -> None:
        payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call_1", "to": "+5511999999999"},
                "endedReason": "assistant-forwarded-call",
                "artifact": {"transcript": "must not be retained"},
            }
        }
        with patch("app.api.routes.vapi_events.SessionLocal", self.session_local):
            response = await ingest_vapi_event(
                self._request({"x-webhook-secret": "secret"}),
                VapiServerEvent(**payload),
                self.settings,
            )
        self.assertEqual(204, response.status_code)
        with self.session_local() as session:
            event = session.scalar(select(CallEvent))
            count = session.scalar(select(func.count(CallEvent.id)))
            receipt = session.scalar(select(VapiWebhookReceipt))
        self.assertEqual(1, count)
        self.assertEqual("vapi_native_transfer_completed", event.event_type)
        self.assertNotIn("transcript", str(event.payload_masked))
        self.assertNotIn("transcript", str(receipt.payload_sanitized))

    async def test_records_normal_customer_end_without_transcript(self) -> None:
        payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call_customer_end", "to": "+5511999999999"},
                "endedReason": "customer-ended-call",
                "artifact": {"transcript": "must not be retained"},
            }
        }
        with patch("app.api.routes.vapi_events.SessionLocal", self.session_local):
            response = await ingest_vapi_event(
                self._request({"x-webhook-secret": "secret"}),
                VapiServerEvent(**payload),
                self.settings,
            )
        self.assertEqual(204, response.status_code)
        with self.session_local() as session:
            event = session.scalar(select(CallEvent))
            receipt = session.scalar(select(VapiWebhookReceipt))
        self.assertEqual("vapi_normal_call_completed", event.event_type)
        self.assertEqual("ENCERRADA_USUARIO", event.final_state)
        self.assertTrue(event.ok)
        self.assertNotIn("transcript", str(event.payload_masked))
        self.assertNotIn("transcript", str(receipt.payload_sanitized))
