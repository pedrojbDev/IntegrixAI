import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.ops.report_delivery_service import run_daily_operational_report_if_due
from app.db import Base
from app.models.call_event import CallEvent
from app.models.ops_sync_state import OpsSyncState


class DailyReportDeliveryTests(unittest.TestCase):
    def _session_local(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        return sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _settings(self) -> Settings:
        return Settings(
            _env_file=None,
            db_enabled=True,
            ops_cost_v2_enabled=True,
            daily_report_enabled=True,
            daily_report_tenant_id="tenant_a",
            daily_report_recipients="pedro@example.com,ops@example.com",
            daily_report_period_days=7,
            smtp_host="smtp.mail.test",
            smtp_from_email="reports@integrix.test",
        )

    def test_sends_once_per_brasilia_day(self) -> None:
        session_local = self._session_local()
        now = datetime(2026, 7, 9, 7, 5, tzinfo=ZoneInfo("America/Sao_Paulo"))
        sent: list[tuple[bytes, str]] = []

        with session_local() as session:
            session.add(
                CallEvent(
                    tenant_id="tenant_a",
                    call_id="call_daily_report",
                    tool_call_id="tc_daily_report",
                    tool_name="search_providers",
                    event_type="tool_completed",
                    final_state="RESOLVIDA_AUTOMATICO",
                    ok=True,
                    duration_ms=550,
                    error_code=None,
                    payload_masked={},
                    created_at=now.astimezone(timezone.utc) - timedelta(minutes=5),
                )
            )
            session.add(
                OpsSyncState(
                    provider="vapi_costs",
                    last_synced_at=now.astimezone(timezone.utc) - timedelta(minutes=2),
                    last_successful_run_at=now.astimezone(timezone.utc)
                    - timedelta(minutes=2),
                    updated_at=now.astimezone(timezone.utc) - timedelta(minutes=2),
                    last_run_stats_json={"missing_fx": 0},
                )
            )
            session.commit()

        def email_sender(_: Settings, report_pdf: bytes, filename: str) -> None:
            sent.append((report_pdf, filename))

        delivered = run_daily_operational_report_if_due(
            self._settings(),
            now=now,
            session_factory=session_local,
            email_sender=email_sender,
        )
        duplicate = run_daily_operational_report_if_due(
            self._settings(),
            now=now + timedelta(hours=2),
            session_factory=session_local,
            email_sender=email_sender,
        )

        self.assertTrue(delivered)
        self.assertFalse(duplicate)
        self.assertEqual(1, len(sent))
        self.assertTrue(sent[0][0].startswith(b"%PDF-"))
        self.assertEqual("relatorio-operacional-2026-07-09.pdf", sent[0][1])

        with session_local() as session:
            state = session.get(OpsSyncState, "daily_operational_report_email")
            self.assertIsNotNone(state)
            self.assertIsNotNone(state.last_synced_at)

    def test_does_not_send_before_the_scheduled_hour(self) -> None:
        session_local = self._session_local()
        sent: list[bytes] = []

        delivered = run_daily_operational_report_if_due(
            self._settings(),
            now=datetime(2026, 7, 9, 6, 59, tzinfo=ZoneInfo("America/Sao_Paulo")),
            session_factory=session_local,
            email_sender=lambda _, report_pdf, __: sent.append(report_pdf),
        )

        self.assertFalse(delivered)
        self.assertEqual([], sent)

    def test_does_not_send_when_cost_sync_is_stale(self) -> None:
        session_local = self._session_local()
        now = datetime(2026, 7, 9, 7, 5, tzinfo=ZoneInfo("America/Sao_Paulo"))
        sent: list[bytes] = []

        delivered = run_daily_operational_report_if_due(
            self._settings(),
            now=now,
            session_factory=session_local,
            email_sender=lambda _, report_pdf, __: sent.append(report_pdf),
        )

        self.assertFalse(delivered)
        self.assertEqual([], sent)


if __name__ == "__main__":
    unittest.main()
