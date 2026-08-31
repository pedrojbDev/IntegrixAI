import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.ops.dashboard_service import get_costs, get_health, get_overview, get_resilience, get_tools
from app.core.ops.report_service import build_operational_report_pdf
from app.db import Base
from app.models.call_event import CallEvent
from app.models.exchange_rate import ExchangeRate
from app.models.ops_sync_state import OpsSyncState
from app.models.tool_invocation import ToolBusinessErrorAttempt
from app.models.vapi_call_cost import VapiCallCost


class DashboardServiceTests(unittest.TestCase):
    def _session_local(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        return sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def test_health_and_resilience_surface_operational_signals(self) -> None:
        session_local = self._session_local()
        now = datetime.now(timezone.utc)

        with session_local() as session:
            session.add_all(
                [
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="call_1",
                        tool_call_id="tc_1",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="RESOLVIDA_AUTOMATICO",
                        ok=True,
                        duration_ms=1200,
                        error_code=None,
                        payload_masked={},
                        created_at=now - timedelta(minutes=5),
                    ),
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="call_2",
                        tool_call_id="tc_2",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="TRANSFERIDA_HUMANO",
                        ok=False,
                        duration_ms=2400,
                        error_code="VALIDATION",
                        payload_masked={},
                        created_at=now - timedelta(minutes=4),
                    ),
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="call_1",
                        tool_call_id="tc_1",
                        tool_name="search_providers",
                        event_type="idempotency_hit",
                        final_state="RESOLVIDA_AUTOMATICO",
                        ok=True,
                        duration_ms=0,
                        error_code=None,
                        payload_masked={},
                        created_at=now - timedelta(minutes=2),
                    ),
                    ToolBusinessErrorAttempt(
                        tenant_id="tenant_a",
                        call_id="call_2",
                        tool_name="search_providers",
                        field="cpf",
                        upstream_code="CPF_INVALIDO",
                        attempts=2,
                        created_at=now - timedelta(minutes=3),
                        updated_at=now - timedelta(minutes=1),
                    ),
                    VapiCallCost(
                        call_id="call_1",
                        tenant_id="tenant_a",
                        to_number="+5511999999999",
                        started_at=now - timedelta(minutes=5),
                        ended_at=now - timedelta(minutes=4),
                        duration_seconds=60,
                        assistant_id="asst_1",
                        status="ended",
                        cost_total_usd=1.1,
                        cost_breakdown_json={"total": 1.1},
                        synced_at=now - timedelta(minutes=1),
                    ),
                    VapiCallCost(
                        call_id="call_2",
                        tenant_id="tenant_a",
                        to_number="+5511999999999",
                        started_at=now - timedelta(minutes=4),
                        ended_at=now - timedelta(minutes=3),
                        duration_seconds=60,
                        assistant_id="asst_1",
                        status="ended",
                        cost_total_usd=2.2,
                        cost_breakdown_json={"total": 2.2},
                        synced_at=now - timedelta(minutes=1),
                    ),
                    OpsSyncState(
                        provider="vapi_costs",
                        last_synced_at=now - timedelta(minutes=1),
                        updated_at=now - timedelta(minutes=1),
                    ),
                ]
            )
            session.commit()

            health = get_health(
                session,
                window="24h",
                tenant_id="tenant_a",
                assistant_id="asst_1",
            )
            costs = get_costs(
                session,
                window="24h",
                tenant_id="tenant_a",
                assistant_id="asst_1",
            )
            resilience = get_resilience(
                session,
                window="24h",
                tenant_id="tenant_a",
                assistant_id="asst_1",
            )

        self.assertEqual("warning", health["health_state"])
        self.assertEqual(1, health["counters"]["idempotency_hits"])
        self.assertEqual(1, health["counters"]["repeated_business_errors"])
        self.assertEqual("fresh", health["sync"]["freshness_state"])
        self.assertEqual(120.0, costs["summary"]["total_duration_seconds"])
        self.assertEqual(60.0, costs["summary"]["avg_duration_seconds"])
        self.assertEqual(2, costs["summary"]["calls_with_duration"])
        self.assertTrue(costs["series"][0]["duration_seconds"] > 0)
        self.assertEqual(1, resilience["summary"]["idempotency_hits"])
        self.assertEqual(1, resilience["summary"]["repeated_business_errors"])
        self.assertTrue(resilience["series"]["failed_calls"])
        self.assertFalse(resilience["series"]["technical_failure_events"])
        self.assertTrue(resilience["series"]["idempotency_hits"])
        self.assertTrue(resilience["series"]["repeated_business_errors"])
        self.assertEqual("search_providers", resilience["top_failure_tools"][0]["tool_name"])
        self.assertEqual("search_providers", resilience["business_error_tools"][0]["tool_name"])

    def test_v2_classifies_successful_handoff_and_technical_failures_independently(self) -> None:
        session_local = self._session_local()
        now = datetime.now(timezone.utc)

        def event(
            call_id: str,
            tool_name: str,
            *,
            ok: bool,
            final_state: str,
            error_code: str | None = None,
            minutes_ago: int = 1,
            tenant_id: str = "tenant_a",
        ) -> CallEvent:
            return CallEvent(
                tenant_id=tenant_id,
                call_id=call_id,
                tool_call_id=f"{call_id}-{tool_name}-{minutes_ago}",
                tool_name=tool_name,
                event_type="tool_completed",
                final_state=final_state,
                ok=ok,
                duration_ms=500,
                error_code=error_code,
                payload_masked={},
                created_at=now - timedelta(minutes=minutes_ago),
            )

        with session_local() as session:
            session.add_all(
                [
                    event("automatic", "search_providers", ok=True, final_state="RESOLVIDA_AUTOMATICO", minutes_ago=8),
                    event("handoff", "search_providers", ok=True, final_state="RESOLVIDA_AUTOMATICO", minutes_ago=7),
                    event("handoff", "handoff_human", ok=True, final_state="TRANSFERIDA_HUMANO", minutes_ago=6),
                    event("validation", "search_providers", ok=False, final_state="TRANSFERIDA_HUMANO", error_code="VALIDATION", minutes_ago=5),
                    event("technical", "search_providers", ok=False, final_state="TRANSFERIDA_HUMANO", error_code="TIMEOUT", minutes_ago=4),
                    event("technical", "handoff_human", ok=True, final_state="TRANSFERIDA_HUMANO", minutes_ago=3),
                    event("handoff", "handoff_human", ok=True, final_state="TRANSFERIDA_HUMANO", tenant_id="tenant_b", minutes_ago=2),
                ]
            )
            session.commit()

            overview = get_overview(session, window="24h", tenant_id="tenant_a", assistant_id=None)
            tools = get_tools(session, window="24h", tenant_id="tenant_a", assistant_id=None)
            resilience = get_resilience(session, window="24h", tenant_id="tenant_a", assistant_id=None)

        self.assertEqual("v2", overview["metric_version"])
        self.assertEqual(4, overview["kpis"]["total_calls"])
        self.assertEqual(1, overview["kpis"]["automated_resolution_calls"])
        self.assertEqual(2, overview["kpis"]["successful_handoff_calls"])
        self.assertEqual(1, overview["kpis"]["unresolved_calls"])
        self.assertEqual(1, overview["kpis"]["technical_failure_events"])
        self.assertEqual(6, overview["kpis"]["tool_execution_count"])
        self.assertEqual(16.67, overview["kpis"]["technical_failure_rate_pct"])
        self.assertEqual(2, sum(point["successful_handoffs"] for point in overview["series"]))

        tools_by_name = {item["tool_name"]: item for item in tools["items"]}
        self.assertEqual(1, tools_by_name["search_providers"]["technical_failure_events"])
        self.assertEqual(0, tools_by_name["handoff_human"]["technical_failure_events"])
        self.assertEqual(1, resilience["summary"]["technical_failure_events"])
        self.assertTrue(resilience["series"]["technical_failure_events"])

    def test_operational_report_is_a_pdf_for_the_requested_tenant(self) -> None:
        session_local = self._session_local()
        now = datetime.now(timezone.utc)

        with session_local() as session:
            session.add(
                CallEvent(
                    tenant_id="tenant_a",
                    call_id="call_report",
                    tool_call_id="tc_report",
                    tool_name="search_providers",
                    event_type="tool_completed",
                    final_state="RESOLVIDA_AUTOMATICO",
                    ok=True,
                    duration_ms=900,
                    error_code=None,
                    payload_masked={},
                    created_at=now - timedelta(days=2),
                )
            )
            session.commit()

            report_pdf = build_operational_report_pdf(
                session,
                period_days=15,
                tenant_id="tenant_a",
                assistant_id=None,
            )

        self.assertTrue(report_pdf.startswith(b"%PDF-"))
        self.assertGreater(len(report_pdf), 1_000)

    def test_cost_window_uses_started_at_and_preserves_null_vs_zero(self) -> None:
        session_local = self._session_local()
        now = datetime.now(timezone.utc)
        with session_local() as session:
            session.add_all(
                [
                    VapiCallCost(
                        call_id="missing",
                        tenant_id="tenant_a",
                        started_at=now - timedelta(minutes=10),
                        cost_total_usd=None,
                        synced_at=now - timedelta(days=20),
                        is_verified=True,
                    ),
                    VapiCallCost(
                        call_id="zero",
                        tenant_id="tenant_a",
                        started_at=now - timedelta(minutes=9),
                        cost_total_usd=Decimal("0"),
                        cost_total_brl=Decimal("0"),
                        synced_at=now - timedelta(days=20),
                        is_verified=True,
                    ),
                    VapiCallCost(
                        call_id="old-call-synced-now",
                        tenant_id="tenant_a",
                        started_at=now - timedelta(days=2),
                        cost_total_usd=Decimal("99"),
                        synced_at=now,
                        is_verified=True,
                    ),
                    VapiCallCost(
                        call_id="other-tenant",
                        tenant_id="tenant_b",
                        started_at=now - timedelta(minutes=8),
                        cost_total_usd=Decimal("50"),
                        synced_at=now,
                        is_verified=True,
                    ),
                    VapiCallCost(
                        call_id="quarantine",
                        tenant_id=None,
                        started_at=now - timedelta(minutes=7),
                        cost_total_usd=Decimal("50"),
                        synced_at=now,
                        is_verified=True,
                    ),
                    VapiCallCost(
                        call_id="legacy-unverified",
                        tenant_id="tenant_a",
                        started_at=now - timedelta(minutes=6),
                        cost_total_usd=Decimal("50"),
                        synced_at=now,
                        is_verified=False,
                    ),
                ]
            )
            session.commit()
            costs = get_costs(
                session,
                window="24h",
                tenant_id="tenant_a",
                assistant_id=None,
            )

        self.assertEqual(2, costs["summary"]["vapi_calls"])
        self.assertEqual(1, costs["summary"]["calls_with_cost"])
        self.assertEqual(1, costs["summary"]["calls_without_cost"])
        self.assertEqual(50.0, costs["summary"]["coverage_pct"])
        self.assertEqual(0.0, costs["summary"]["total_cost_usd"])

    def test_ptax_conversion_and_tool_metrics_remain_separate(self) -> None:
        session_local = self._session_local()
        now = datetime.now(timezone.utc)
        call_date = now.astimezone(ZoneInfo("America/Sao_Paulo")).date()
        with session_local() as session:
            session.add(
                ExchangeRate(
                    rate_date=call_date,
                    base_currency="USD",
                    quote_currency="BRL",
                    sale_rate=Decimal("5.12345678"),
                    source="BCB_PTAX",
                    is_provisional=False,
                )
            )
            session.add(
                VapiCallCost(
                    call_id="financial-call",
                    tenant_id="tenant_a",
                    started_at=now - timedelta(minutes=10),
                    cost_total_usd=Decimal("1.20000000"),
                    cost_total_brl=Decimal("6.14814814"),
                    usd_brl_rate=Decimal("5.12345678"),
                    fx_rate_date=call_date,
                    cost_transport_usd=Decimal("0.2"),
                    cost_llm_usd=Decimal("0.8"),
                    cost_other_usd=Decimal("0.2"),
                    synced_at=now,
                    is_verified=True,
                )
            )
            session.add(
                CallEvent(
                    tenant_id="tenant_a",
                    call_id="financial-call",
                    tool_call_id="tc_financial",
                    tool_name="search_providers",
                    event_type="tool_completed",
                    final_state="RESOLVIDA_AUTOMATICO",
                    ok=True,
                    duration_ms=900,
                    error_code=None,
                    payload_masked={},
                    created_at=now - timedelta(minutes=9),
                )
            )
            session.commit()
            costs = get_costs(
                session,
                window="24h",
                tenant_id="tenant_a",
                assistant_id=None,
            )
            tools = get_tools(
                session,
                window="24h",
                tenant_id="tenant_a",
                assistant_id=None,
            )

        self.assertEqual(6.15, costs["summary"]["total_cost_brl"])
        self.assertEqual(1, costs["reconciliation"]["component_adjustment_calls"])
        self.assertEqual(100.0, costs["reconciliation"]["linkage_coverage_pct"])
        self.assertNotIn("total_cost_usd", tools["items"][0])
        self.assertNotIn("avg_cost_per_call_usd", tools["items"][0])


if __name__ == "__main__":
    unittest.main()
