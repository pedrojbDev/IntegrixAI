import unittest
from queue import Full
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.audit.service import (
    record_call_event,
    stop_audit_worker,
    wait_for_audit_queue,
)
from app.core.metrics.service import metrics_store
from app.db import Base
from app.models.call_event import CallEvent


class AuditServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        stop_audit_worker()
        metrics_store.reset()

    def tearDown(self) -> None:
        stop_audit_worker()
        metrics_store.reset()

    def test_async_audit_enqueues_and_worker_writes_batch(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        settings = Settings(
            _env_file=None,
            db_enabled=True,
            audit_write_mode="async",
            audit_queue_max_size=10,
            audit_batch_size=1,
            audit_flush_interval_seconds=0.05,
        )

        with patch("app.core.audit.service.SessionLocal", session_local):
            record_call_event(
                settings=settings,
                tenant_id="tenant_a",
                call_id="call_123",
                tool_name="handoff_human",
                event_type="tool_completed",
                final_state="TRANSFERIDA_HUMANO",
                ok=True,
                duration_ms=12.5,
                error_code=None,
                payload={"token": "secret-token", "safe": "value"},
            )

            self.assertTrue(wait_for_audit_queue(timeout_seconds=2.0))
            with session_local() as session:
                count = session.execute(select(func.count(CallEvent.id))).scalar_one()
                row = session.execute(select(CallEvent)).scalar_one()

        self.assertEqual(1, count)
        self.assertEqual("tenant_a", row.tenant_id)
        self.assertEqual("***", row.payload_masked["token"])
        self.assertEqual("value", row.payload_masked["safe"])
        self.assertEqual(1, metrics_store.snapshot()["ops"]["audit_events_enqueued"])
        self.assertEqual(1, metrics_store.snapshot()["ops"]["audit_events_written"])

    def test_async_audit_queue_full_is_fail_open(self) -> None:
        class FullQueue:
            def put_nowait(self, _event):
                raise Full

        class FakeWorker:
            queue = FullQueue()

        settings = Settings(_env_file=None, db_enabled=True, audit_write_mode="async")

        with patch("app.core.audit.service._get_audit_worker", return_value=FakeWorker()):
            record_call_event(
                settings=settings,
                tenant_id="tenant_a",
                call_id="call_123",
                tool_name="handoff_human",
                event_type="tool_completed",
                final_state="TRANSFERIDA_HUMANO",
                ok=True,
                duration_ms=12.5,
                error_code=None,
                payload={},
            )

        self.assertEqual(1, metrics_store.snapshot()["ops"]["audit_events_dropped"])


if __name__ == "__main__":
    unittest.main()
