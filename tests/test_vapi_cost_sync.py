import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.ops.cost_sync_service import ParsedCallCost, VapiCostSyncService
from app.db import Base
from app.models.ops_sync_state import OpsSyncState
from app.models.vapi_call_cost import VapiCallCost


def production_settings(**overrides):
    values = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql+psycopg://app:secret@db.prod.internal:5432/integrix",
        "db_enabled": True,
        "data_mode": "external_api",
        "default_tenant": "tenant_default",
        "tenant_map": {"+5511999999999": "tenant_a"},
        "webhook_secret": "secret",
        "ops_dashboard_token": "ops-token",
        "audit_write_mode": "async",
        "external_api_base_url": "https://api.customer-prod.internal",
        "external_api_auth_type": "basic",
        "external_api_username": "user",
        "external_api_password": "password",
    }
    values.update(overrides)
    return Settings(**values)


class VapiCostSyncTests(unittest.TestCase):
    def _session_local(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        return sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def test_parse_call_keeps_resolution_and_official_cost_components(self) -> None:
        settings = Settings(
            _env_file=None,
            default_tenant="tenant_default",
            tenant_map={"+5511999999999": "tenant_a"},
        )
        service = VapiCostSyncService(settings)

        parsed = service._parse_call(
            {
                "id": "call_123",
                "to": "+5511999999999",
                "createdAt": "2026-04-08T11:59:00Z",
                "updatedAt": "2026-04-08T12:06:00Z",
                "startedAt": "2026-04-08T12:00:00Z",
                "endedAt": "2026-04-08T12:05:00Z",
                "assistantId": "asst_123",
                "phoneNumberId": "phone_123",
                "status": "ended",
                "cost": "1.23000000",
                "costBreakdown": {
                    "transport": 0.20,
                    "stt": 0.10,
                    "llm": 0.30,
                    "tts": 0.20,
                    "vapi": 0.40,
                },
            }
        )

        self.assertIsNotNone(parsed)
        self.assertEqual("tenant_a", parsed.tenant_id)
        self.assertEqual("did_map", parsed.tenant_resolution_source)
        self.assertEqual("phone_123", parsed.phone_number_id)
        self.assertEqual(Decimal("1.23000000"), parsed.cost_total_usd)
        self.assertEqual(Decimal("0.03000000"), parsed.components["other"])

    def test_missing_cost_is_null_and_explicit_zero_remains_zero(self) -> None:
        service = VapiCostSyncService(
            Settings(_env_file=None, tenant_map={"+5511999999999": "tenant_a"})
        )
        base = {
            "to": "+5511999999999",
            "startedAt": "2026-04-08T12:00:00Z",
        }

        missing = service._parse_call({"id": "missing", **base})
        zero = service._parse_call({"id": "zero", "cost": 0, **base})

        self.assertIsNone(missing.cost_total_usd)
        self.assertEqual(Decimal("0"), zero.cost_total_usd)

    def test_parse_call_quarantines_unresolved_tenant_in_production(self) -> None:
        service = VapiCostSyncService(production_settings())

        parsed = service._parse_call(
            {
                "id": "call_123",
                "to": "+5511888888888",
                "startedAt": "2026-04-08T12:00:00Z",
                "cost": 1.23,
            }
        )

        self.assertIsNotNone(parsed)
        self.assertIsNone(parsed.tenant_id)
        self.assertEqual("default_tenant", parsed.tenant_resolution_source)

    def test_phone_number_and_assistant_maps_resolve_tenant(self) -> None:
        service = VapiCostSyncService(
            Settings(
                _env_file=None,
                tenant_assistant_map={"asst_1": "tenant_assistant"},
                tenant_phone_number_map={"phone_1": "tenant_phone"},
            )
        )

        phone = service._parse_call({"id": "phone", "phoneNumberId": "phone_1"})
        assistant = service._parse_call({"id": "assistant", "assistantId": "asst_1"})

        self.assertEqual("tenant_phone", phone.tenant_id)
        self.assertEqual("phone_number_id_map", phone.tenant_resolution_source)
        self.assertEqual("tenant_assistant", assistant.tenant_id)
        self.assertEqual("assistant_map", assistant.tenant_resolution_source)

    def test_upsert_is_idempotent_and_marks_rows_verified(self) -> None:
        session_local = self._session_local()
        service = VapiCostSyncService(Settings(_env_file=None))
        synced_at = datetime.now(timezone.utc)

        with session_local() as session:
            first = ParsedCallCost(
                call_id="call_123",
                tenant_id="tenant_a",
                to_number="+5511999999999",
                started_at=synced_at,
                ended_at=None,
                duration_seconds=60.0,
                assistant_id="asst_1",
                status="ended",
                cost_total_usd=Decimal("1.0"),
                cost_breakdown_json={},
            )
            created, updated = service._upsert_cost_batch(session, [first], synced_at)
            session.commit()
            first.cost_total_usd = Decimal("2.5")
            first.duration_seconds = 120.0
            created_again, updated_again = service._upsert_cost_batch(
                session, [first], synced_at
            )
            session.commit()
            row = session.get(VapiCallCost, "call_123")

        self.assertEqual((1, 0), (created, updated))
        self.assertEqual((0, 1), (created_again, updated_again))
        self.assertEqual(Decimal("2.50000000"), row.cost_total_usd)
        self.assertTrue(row.is_verified)

    def test_saturated_windows_are_recursively_subdivided(self) -> None:
        service = VapiCostSyncService(
            Settings(_env_file=None, ops_cost_sync_page_size=2)
        )
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        end = start + timedelta(seconds=8)

        def fetch(left, right, _):
            if (right - left).total_seconds() > 2:
                return [{"id": f"{left}-a"}, {"id": f"{left}-b"}]
            return [{"id": f"{left}-only"}]

        with patch.object(service, "_fetch_calls", side_effect=fetch):
            calls = service._fetch_complete_range(start, end, "createdAt")

        self.assertGreaterEqual(len(calls), 4)

    def test_unsplittable_saturated_window_fails_closed(self) -> None:
        service = VapiCostSyncService(
            Settings(_env_file=None, ops_cost_sync_page_size=2)
        )
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        with patch.object(
            service,
            "_fetch_calls",
            return_value=[{"id": "a"}, {"id": "b"}],
        ):
            with self.assertRaisesRegex(RuntimeError, "cursor not advanced"):
                service._fetch_complete_range(
                    start,
                    start + timedelta(seconds=1),
                    "createdAt",
                )

    def test_thousand_call_limit_is_split_without_truncation(self) -> None:
        service = VapiCostSyncService(
            Settings(_env_file=None, ops_cost_sync_page_size=1000)
        )
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        end = start + timedelta(seconds=4)

        def fetch(left, right, _):
            seconds = int((right - left).total_seconds())
            size = 1000 if seconds > 2 else 600
            return [
                {"id": f"{left.isoformat()}-{index}"}
                for index in range(size)
            ]

        with patch.object(service, "_fetch_calls", side_effect=fetch):
            calls = service._fetch_complete_range(start, end, "createdAt")

        self.assertEqual(1200, len(calls))

    def test_incremental_uses_updated_at_overlap_and_advances_cursor_after_commit(self) -> None:
        session_local = self._session_local()
        settings = Settings(
            _env_file=None,
            vapi_api_key="vapi-key",
            ops_cost_sync_overlap_minutes=10,
            tenant_map={"+5511999999999": "tenant_a"},
        )
        service = VapiCostSyncService(settings)
        cursor = datetime.now(timezone.utc) - timedelta(minutes=30)
        captured: list[tuple[datetime, datetime, str]] = []
        with session_local() as session:
            session.add(
                OpsSyncState(
                    provider="vapi_costs",
                    cursor_updated_at=cursor,
                    last_successful_run_at=cursor,
                )
            )
            session.commit()

            def fetch(start, end, field):
                captured.append((start, end, field))
                return [
                    {
                        "id": "late-update",
                        "to": "+5511999999999",
                        "createdAt": (cursor - timedelta(days=1)).isoformat(),
                        "updatedAt": (cursor + timedelta(minutes=1)).isoformat(),
                        "startedAt": (cursor - timedelta(days=1)).isoformat(),
                        "cost": 2.0,
                    }
                ]

            with (
                patch.object(service, "_fetch_complete_range", side_effect=fetch),
                patch.object(service.ptax, "ensure_rates", return_value=0),
                patch.object(service.ptax, "rate_for_call", return_value=(None, None, False)),
            ):
                result = service.sync(session)
            state = session.get(OpsSyncState, "vapi_costs")
            row = session.get(VapiCallCost, "late-update")

        self.assertEqual("incremental", result["mode"])
        self.assertEqual("updatedAt", captured[0][2])
        self.assertAlmostEqual(
            (captured[0][0] - (cursor - timedelta(minutes=10))).total_seconds(),
            0,
            delta=0.01,
        )
        stored_cursor = state.cursor_updated_at
        if stored_cursor.tzinfo is None:
            stored_cursor = stored_cursor.replace(tzinfo=timezone.utc)
        self.assertGreater(stored_cursor, cursor)
        self.assertEqual(Decimal("2.00000000"), row.cost_total_usd)

    def test_initial_sync_backfills_created_at_in_daily_blocks(self) -> None:
        session_local = self._session_local()
        service = VapiCostSyncService(
            Settings(
                _env_file=None,
                vapi_api_key="vapi-key",
                ops_cost_backfill_days=2,
            )
        )
        captured: list[tuple[datetime, datetime, str]] = []
        with self._session_local()() as session:
            def fetch(start, end, field):
                captured.append((start, end, field))
                return []

            with patch.object(service, "_fetch_complete_range", side_effect=fetch):
                result = service.sync(session)
            state = session.get(OpsSyncState, "vapi_costs")

        self.assertEqual("backfill", result["mode"])
        self.assertGreaterEqual(len(captured), 2)
        self.assertTrue(all(item[2] == "createdAt" for item in captured))
        self.assertIsNotNone(state.cursor_updated_at)
        self.assertIsNotNone(state.last_successful_run_at)

    def test_concurrent_worker_that_loses_lock_does_not_sync(self) -> None:
        service = VapiCostSyncService(
            Settings(_env_file=None, vapi_api_key="vapi-key")
        )
        with self._session_local()() as session:
            with patch.object(service, "_try_lock", return_value=False):
                result = service.sync(session)

        self.assertTrue(result["locked"])
        self.assertEqual(0, result["processed"])


if __name__ == "__main__":
    unittest.main()
