import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.ops.cost_sync_service import ParsedCallCost, VapiCostSyncService
from app.db import Base
from app.models.ops_sync_state import OpsSyncState
from app.models.call_event import CallEvent
from app.models.voice_call import VoiceCall
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

    def test_parse_call_ignores_caller_ani_when_resolving_tenant(self) -> None:
        service = VapiCostSyncService(
            production_settings(
                tenant_map={"+5511888888888": "tenant_victim"},
            )
        )

        parsed = service._parse_call(
            {
                "id": "ani-call",
                "customer": {"number": "+5511888888888"},
                "createdAt": "2026-04-08T11:59:00Z",
                "startedAt": "2026-04-08T12:00:00Z",
            }
        )

        self.assertIsNotNone(parsed)
        self.assertIsNone(parsed.to_number)
        self.assertIsNone(parsed.tenant_id)
        self.assertNotEqual("tenant_victim", parsed.tenant_resolution_source)

    def test_parse_call_still_resolves_real_dnis_number(self) -> None:
        service = VapiCostSyncService(
            Settings(
                _env_file=None,
                tenant_map={"+5511999999999": "tenant_a"},
            )
        )

        parsed = service._parse_call(
            {
                "id": "dnis-call",
                "to": "+5511999999999",
                "createdAt": "2026-04-08T11:59:00Z",
                "startedAt": "2026-04-08T12:00:00Z",
            }
        )

        self.assertIsNotNone(parsed)
        self.assertEqual("tenant_a", parsed.tenant_id)

    def test_parse_call_resolves_nested_phone_number_dnis(self) -> None:
        service = VapiCostSyncService(
            Settings(
                _env_file=None,
                tenant_map={"+5511999999999": "tenant_a"},
            )
        )

        parsed = service._parse_call(
            {
                "id": "nested-dnis-call",
                "phoneNumber": {"number": "+5511999999999"},
                "startedAt": "2026-04-08T12:00:00Z",
            }
        )

        self.assertIsNotNone(parsed)
        self.assertEqual("+5511999999999", parsed.to_number)
        self.assertEqual("tenant_a", parsed.tenant_id)

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

    def test_parse_call_retains_only_finite_voice_quality_metrics(self) -> None:
        """Removing the metric extractor must leave quality diagnostics empty."""
        service = VapiCostSyncService(
            Settings(_env_file=None, tenant_map={"+5511999999999": "tenant_a"})
        )

        parsed = service._parse_call(
            {
                "id": "quality-call",
                "to": "+5511999999999",
                "startedAt": "2026-09-08T12:00:00Z",
                "artifact": {
                    "performanceMetrics": {
                        "turnLatencyAverage": 842.5,
                        "numAssistantInterrupted": 2,
                    },
                    "messages": [{"role": "user", "message": "private"}],
                    "transcript": "private",
                },
            }
        )

        self.assertEqual(842.5, parsed.turn_latency_average_ms)
        self.assertEqual(2, parsed.assistant_interruptions)
        self.assertNotIn("artifact", parsed.raw_call_json)
        self.assertNotIn("private", str(parsed.raw_call_json))

    def test_parse_call_discards_missing_malformed_and_nonfinite_voice_quality_metrics(self) -> None:
        """Accepting malformed provider metrics would corrupt dashboard aggregates."""
        service = VapiCostSyncService(Settings(_env_file=None))

        for index, metrics in enumerate(
            (
                {},
                {"turnLatencyAverage": "842.5", "numAssistantInterrupted": "2"},
                {"turnLatencyAverage": float("nan"), "numAssistantInterrupted": float("inf")},
                {"turnLatencyAverage": Decimal("sNaN"), "numAssistantInterrupted": Decimal("sNaN")},
                {"turnLatencyAverage": -1, "numAssistantInterrupted": -1},
            )
        ):
            with self.subTest(metrics=metrics):
                parsed = service._parse_call(
                    {
                        "id": f"invalid-quality-{index}",
                        "artifact": {"performanceMetrics": metrics},
                    }
                )

                self.assertIsNone(parsed.turn_latency_average_ms)
                self.assertIsNone(parsed.assistant_interruptions)

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

    def test_upsert_does_not_rewrite_foreign_existing_call(self) -> None:
        session_local = self._session_local()
        now = datetime.now(timezone.utc)
        service = VapiCostSyncService(Settings(_env_file=None))

        with session_local() as session:
            session.add(
                VapiCallCost(
                    call_id="shared-call",
                    tenant_id="tenant_b",
                    assistant_id="assistant_b",
                    cost_total_usd=Decimal("9.00"),
                    started_at=now - timedelta(minutes=5),
                    synced_at=now,
                )
            )
            session.commit()

            spoofed = ParsedCallCost(
                call_id="shared-call",
                tenant_id="tenant_a",
                to_number="+5511999999999",
                started_at=now - timedelta(minutes=5),
                ended_at=now - timedelta(minutes=4),
                duration_seconds=60.0,
                assistant_id="assistant_a",
                status="ended",
                cost_total_usd=Decimal("1.10"),
                cost_breakdown_json={"total": 1.1},
            )

            with patch.object(service.ptax, "rate_for_call", return_value=(None, None, False)):
                service._upsert_cost_batch(session, [spoofed], now)

            session.commit()
            unchanged = session.get(VapiCallCost, "shared-call")

        self.assertEqual("tenant_b", unchanged.tenant_id)
        self.assertEqual(Decimal("9.00000000"), unchanged.cost_total_usd)

    def test_sync_drops_foreign_call_before_fx_shadow_upsert_and_reconcile(self) -> None:
        session_local = self._session_local()
        now = datetime.now(timezone.utc)
        service = VapiCostSyncService(
            Settings(
                _env_file=None,
                vapi_api_key="vapi-key",
                ops_cost_backfill_days=1,
                tenant_map={"+5511999999999": "tenant_a"},
                voice_call_shadow_enabled=True,
            )
        )
        raw_call = {
            "id": "shared-call",
            "to": "+5511999999999",
            "createdAt": (now - timedelta(minutes=5)).isoformat(),
            "updatedAt": now.isoformat(),
            "startedAt": (now - timedelta(minutes=5)).isoformat(),
            "endedAt": (now - timedelta(minutes=4)).isoformat(),
            "status": "ended",
            "endedReason": "customer-ended-call",
            "cost": "1.10",
        }

        with session_local() as session:
            session.add(
                VapiCallCost(
                    call_id="shared-call",
                    tenant_id="tenant_b",
                    assistant_id="assistant_b",
                    cost_total_usd=Decimal("9.00"),
                    started_at=now - timedelta(minutes=5),
                    synced_at=now,
                )
            )
            session.commit()

            with (
                patch.object(service, "_fetch_complete_range", return_value=[raw_call]),
                patch.object(service.ptax, "ensure_rates", return_value=0) as ensure_rates,
                patch.object(service.ptax, "rate_for_call", return_value=(None, None, False)) as rate_for_call,
                patch(
                    "app.core.ops.cost_sync_service.VoiceCallReconciliationService.reconcile",
                    side_effect=RuntimeError("shadow must not run for foreign call"),
                ) as shadow_reconcile,
            ):
                result = service.sync(session)

            unchanged = session.get(VapiCallCost, "shared-call")
            events = session.execute(
                select(CallEvent).where(CallEvent.call_id == "shared-call")
            ).scalars().all()
            voice_calls = session.execute(
                select(VoiceCall).where(VoiceCall.provider_call_id == "shared-call")
            ).scalars().all()

        self.assertEqual(1, result["processed"])
        self.assertEqual(1, result["skipped"])
        self.assertEqual(0, result["updated"])
        self.assertEqual(0, result["missing_fx"])
        ensure_rates.assert_called_once_with(session, set())
        rate_for_call.assert_not_called()
        shadow_reconcile.assert_not_called()
        self.assertEqual("tenant_b", unchanged.tenant_id)
        self.assertEqual(Decimal("9.00000000"), unchanged.cost_total_usd)
        self.assertEqual([], events)
        self.assertEqual([], voice_calls)

    def test_quality_metric_upsert_is_idempotent_and_preserves_legacy_nulls(self) -> None:
        """An upsert must refresh metrics without inventing values for old calls."""
        session_local = self._session_local()
        service = VapiCostSyncService(Settings(_env_file=None))
        synced_at = datetime.now(timezone.utc)

        with session_local() as session:
            session.add(VapiCallCost(call_id="legacy", tenant_id="tenant_a"))
            first = ParsedCallCost(
                call_id="quality-call",
                tenant_id="tenant_a",
                to_number=None,
                started_at=synced_at,
                ended_at=None,
                duration_seconds=None,
                assistant_id="assistant_a",
                status="ended",
                cost_total_usd=None,
                cost_breakdown_json={},
                turn_latency_average_ms=842.5,
                assistant_interruptions=1,
            )
            service._upsert_cost_batch(session, [first], synced_at)
            session.commit()
            first.turn_latency_average_ms = 512.0
            first.assistant_interruptions = 3
            service._upsert_cost_batch(session, [first], synced_at)
            session.commit()
            updated = session.get(VapiCallCost, "quality-call")
            legacy = session.get(VapiCallCost, "legacy")

        self.assertEqual(512.0, updated.turn_latency_average_ms)
        self.assertEqual(3, updated.assistant_interruptions)
        self.assertIsNone(legacy.turn_latency_average_ms)
        self.assertIsNone(legacy.assistant_interruptions)

    def test_voice_quality_backfill_is_tenant_and_created_at_half_open_scoped(self) -> None:
        """Removing either provider scope or createdAt boundary would over-import calls."""
        session_local = self._session_local()
        start = datetime(2026, 9, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=7)
        service = VapiCostSyncService(
            Settings(
                _env_file=None,
                vapi_api_key="vapi-key",
                tenant_assistant_map={"assistant_a": "tenant_a", "assistant_b": "tenant_b"},
                tenant_phone_number_map={"phone_a": "tenant_a", "phone_b": "tenant_b"},
            )
        )
        calls = [
            {
                "id": "tenant-a-in-window",
                "assistantId": "assistant_a",
                "createdAt": (start + timedelta(minutes=1)).isoformat(),
                "startedAt": (start + timedelta(minutes=1)).isoformat(),
                "artifact": {"performanceMetrics": {"turnLatencyAverage": 200, "numAssistantInterrupted": 1}},
            },
            {
                "id": "tenant-b-in-window",
                "assistantId": "assistant_b",
                "createdAt": (start + timedelta(minutes=1)).isoformat(),
                "startedAt": (start + timedelta(minutes=1)).isoformat(),
                "artifact": {"performanceMetrics": {"turnLatencyAverage": 300, "numAssistantInterrupted": 2}},
            },
            {
                "id": "tenant-a-end-boundary",
                "assistantId": "assistant_a",
                "createdAt": end.isoformat(),
                "startedAt": end.isoformat(),
                "artifact": {"performanceMetrics": {"turnLatencyAverage": 400, "numAssistantInterrupted": 3}},
            },
        ]

        with session_local() as session:
            fetched_selectors: list[tuple[str, str] | None] = []

            def fetch(_start, _end, _field, provider_selector=None):
                fetched_selectors.append(provider_selector)
                return calls

            with (
                patch.object(service, "_fetch_calls", side_effect=fetch),
                patch.object(service.ptax, "ensure_rates", return_value=0),
                patch.object(service.ptax, "rate_for_call", return_value=(None, None, False)),
            ):
                result = service.backfill_voice_quality(
                    session,
                    tenant_id="tenant_a",
                    start=start,
                    end=end,
                )
            session.commit()
            rows = session.execute(select(VapiCallCost).order_by(VapiCallCost.call_id)).scalars().all()

        self.assertEqual({("assistantId", "assistant_a"), ("phoneNumberId", "phone_a")}, set(fetched_selectors))
        self.assertTrue(all(selector is not None for selector in fetched_selectors))
        self.assertEqual({"tenant_id": "tenant_a", "processed": 1, "created": 1, "updated": 0, "skipped": 2}, result)
        self.assertEqual(["tenant-a-in-window"], [row.call_id for row in rows])

    def test_voice_quality_backfill_unknown_tenant_fails_before_provider_request(self) -> None:
        service = VapiCostSyncService(Settings(_env_file=None, vapi_api_key="vapi-key"))
        start = datetime(2026, 9, 1, tzinfo=timezone.utc)
        with self._session_local()() as session:
            with patch.object(service, "_fetch_calls") as fetch:
                with self.assertRaisesRegex(ValueError, "provider selector"):
                    service.backfill_voice_quality(
                        session,
                        tenant_id="unknown",
                        start=start,
                        end=start + timedelta(days=1),
                    )
                fetch.assert_not_called()

    def test_voice_quality_backfill_does_not_rewrite_foreign_existing_call(self) -> None:
        session_local = self._session_local()
        start = datetime(2026, 9, 1, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        service = VapiCostSyncService(
            Settings(_env_file=None, vapi_api_key="vapi-key", tenant_assistant_map={"assistant_a": "tenant_a"})
        )
        with session_local() as session:
            foreign = VapiCallCost(
                call_id="shared-call",
                tenant_id="tenant_b",
                assistant_id="assistant_b",
                cost_total_usd=Decimal("9.00"),
                started_at=start + timedelta(minutes=1),
                synced_at=now,
            )
            session.add(foreign)
            session.commit()
            with (
                patch.object(
                    service,
                    "_fetch_calls",
                    return_value=[
                        {
                            "id": "shared-call",
                            "assistantId": "assistant_a",
                            "createdAt": (start + timedelta(minutes=1)).isoformat(),
                            "startedAt": (start + timedelta(minutes=1)).isoformat(),
                            "cost": 1.0,
                            "artifact": {"performanceMetrics": {"turnLatencyAverage": 100, "numAssistantInterrupted": 1}},
                        }
                    ],
                ),
                patch.object(service.ptax, "ensure_rates", return_value=0),
                patch.object(service.ptax, "rate_for_call", return_value=(None, None, False)),
            ):
                result = service.backfill_voice_quality(
                    session,
                    tenant_id="tenant_a",
                    start=start,
                    end=start + timedelta(days=1),
                )
            session.commit()
            unchanged = session.get(VapiCallCost, "shared-call")

        self.assertEqual(0, result["processed"])
        self.assertEqual(1, result["skipped"])
        self.assertEqual("tenant_b", unchanged.tenant_id)
        self.assertEqual(Decimal("9.00000000"), unchanged.cost_total_usd)
        self.assertIsNone(unchanged.turn_latency_average_ms)
        self.assertIsNone(unchanged.assistant_interruptions)

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

    def test_saved_terminal_outcomes_backfill_is_tenant_scoped_and_idempotent(self) -> None:
        session_local = self._session_local()
        service = VapiCostSyncService(Settings(_env_file=None))
        with session_local() as session:
            session.add_all(
                [
                    VapiCallCost(
                        call_id="customer_end",
                        tenant_id="tenant_a",
                        raw_call_json={"endedReason": "customer-ended-call"},
                    ),
                    VapiCallCost(
                        call_id="agent_end",
                        tenant_id="tenant_a",
                        raw_call_json={"endedReason": "assistant-ended-call"},
                    ),
                    VapiCallCost(
                        call_id="other_tenant",
                        tenant_id="tenant_b",
                        raw_call_json={"endedReason": "customer-ended-call"},
                    ),
                ]
            )
            session.commit()

            first = service.reconcile_saved_terminal_outcomes(session, tenant_id="tenant_a")
            session.commit()
            second = service.reconcile_saved_terminal_outcomes(session, tenant_id="tenant_a")
            events = session.execute(
                select(CallEvent).where(CallEvent.event_type == "vapi_normal_call_completed")
            ).scalars().all()

        self.assertEqual({"scanned": 2, "successful_handoffs": 0, "normal_completions": 2}, first)
        self.assertEqual({"scanned": 2, "successful_handoffs": 0, "normal_completions": 0}, second)
        self.assertEqual({"customer_end", "agent_end"}, {event.call_id for event in events})
        self.assertEqual({"ENCERRADA_USUARIO", "ENCERRADA_AGENTE"}, {event.final_state for event in events})


@unittest.skipUnless(
    os.environ.get("VAPI_TEST_DATABASE_URL"),
    "disposable PostgreSQL not configured",
)
class VapiCostSyncPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(os.environ["VAPI_TEST_DATABASE_URL"])
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

    def test_postgres_guard_rejects_foreign_conflict_atomically(self) -> None:
        call_id = f"cost-guard-{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc)
        service = VapiCostSyncService(Settings(_env_file=None))
        incoming = ParsedCallCost(
            call_id=call_id,
            tenant_id="tenant_a",
            to_number="+5511999999999",
            started_at=now,
            ended_at=now + timedelta(minutes=1),
            duration_seconds=60.0,
            assistant_id="assistant_a",
            status="ended",
            cost_total_usd=Decimal("1.10"),
            cost_breakdown_json={},
        )

        with self.sessions() as session:
            session.add(
                VapiCallCost(
                    call_id=call_id,
                    tenant_id="tenant_b",
                    assistant_id="assistant_b",
                    cost_total_usd=Decimal("9.00"),
                    started_at=now,
                    synced_at=now,
                )
            )
            session.commit()

            with patch.object(service.ptax, "rate_for_call", return_value=(None, None, False)):
                result = service._upsert_cost_batch_detailed(
                    session,
                    [incoming],
                    now,
                    ownership_checked=True,
                )
            session.commit()
            unchanged = session.get(VapiCallCost, call_id)

        self.assertEqual((0, 0, 0), result)
        self.assertEqual("tenant_b", unchanged.tenant_id)
        self.assertEqual(Decimal("9.00000000"), unchanged.cost_total_usd)


if __name__ == "__main__":
    unittest.main()
