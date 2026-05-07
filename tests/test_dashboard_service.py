from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.ops.dashboard_service import get_costs, get_overview, get_tools
from app.db import Base
from app.models.call_event import CallEvent
from app.models.vapi_call_cost import VapiCallCost


class DashboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        self.now = datetime.now(timezone.utc)

    def test_overview_uses_latest_tool_completed_event_per_call(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="call_1",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="TRANSFERIDA_HUMANO",
                        ok=False,
                        duration_ms=20.0,
                        payload_masked={},
                        created_at=self.now - timedelta(minutes=20),
                    ),
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="call_1",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="RESOLVIDA_AUTOMATICO",
                        ok=True,
                        duration_ms=10.0,
                        payload_masked={},
                        created_at=self.now - timedelta(minutes=10),
                    ),
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="call_2",
                        tool_name="handoff_human",
                        event_type="tool_completed",
                        final_state="TRANSFERIDA_HUMANO",
                        ok=True,
                        duration_ms=30.0,
                        payload_masked={},
                        created_at=self.now - timedelta(minutes=5),
                    ),
                    CallEvent(
                        tenant_id="tenant_b",
                        call_id="call_3",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="RESOLVIDA_AUTOMATICO",
                        ok=True,
                        duration_ms=99.0,
                        payload_masked={},
                        created_at=self.now - timedelta(minutes=3),
                    ),
                ]
            )
            session.commit()

            result = get_overview(session, window="1h", tenant_id="tenant_a", assistant_id=None)

        self.assertEqual(2, result["kpis"]["total_calls"])
        self.assertEqual(1, result["kpis"]["success_calls"])
        self.assertEqual(1, result["kpis"]["failed_calls"])
        self.assertEqual(1, result["kpis"]["handoff_calls"])
        self.assertEqual(20.0, result["kpis"]["avg_duration_ms"])

    def test_tools_and_costs_are_tenant_scoped(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="call_1",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="RESOLVIDA_AUTOMATICO",
                        ok=True,
                        duration_ms=10.0,
                        payload_masked={},
                        created_at=self.now - timedelta(minutes=10),
                    ),
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="call_2",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="TRANSFERIDA_HUMANO",
                        ok=False,
                        duration_ms=20.0,
                        payload_masked={},
                        created_at=self.now - timedelta(minutes=5),
                    ),
                    CallEvent(
                        tenant_id="tenant_b",
                        call_id="call_3",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="RESOLVIDA_AUTOMATICO",
                        ok=True,
                        duration_ms=99.0,
                        payload_masked={},
                        created_at=self.now - timedelta(minutes=3),
                    ),
                    VapiCallCost(
                        call_id="call_1",
                        tenant_id="tenant_a",
                        cost_total_usd=1.25,
                        synced_at=self.now - timedelta(minutes=10),
                    ),
                    VapiCallCost(
                        call_id="call_2",
                        tenant_id="tenant_a",
                        cost_total_usd=2.75,
                        synced_at=self.now - timedelta(minutes=5),
                    ),
                    VapiCallCost(
                        call_id="call_3",
                        tenant_id="tenant_b",
                        cost_total_usd=100.0,
                        synced_at=self.now - timedelta(minutes=3),
                    ),
                ]
            )
            session.commit()

            tools = get_tools(session, window="1h", tenant_id="tenant_a", assistant_id=None)
            costs = get_costs(session, window="1h", tenant_id="tenant_a", assistant_id=None)

        self.assertEqual(1, len(tools["items"]))
        self.assertEqual("search_providers", tools["items"][0]["tool_name"])
        self.assertEqual(2, tools["items"][0]["total_calls"])
        self.assertEqual(2, tools["items"][0]["unique_calls"])
        self.assertEqual(4.0, tools["items"][0]["total_cost_usd"])
        self.assertEqual(4.0, costs["summary"]["total_cost_usd"])
        self.assertEqual(2, costs["summary"]["calls_with_cost"])

    def test_overview_does_not_assume_call_id_is_global(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="shared_call",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="RESOLVIDA_AUTOMATICO",
                        ok=True,
                        duration_ms=10.0,
                        payload_masked={},
                        created_at=self.now - timedelta(minutes=10),
                    ),
                    CallEvent(
                        tenant_id="tenant_b",
                        call_id="shared_call",
                        tool_name="search_providers",
                        event_type="tool_completed",
                        final_state="TRANSFERIDA_HUMANO",
                        ok=False,
                        duration_ms=20.0,
                        payload_masked={},
                        created_at=self.now - timedelta(minutes=5),
                    ),
                ]
            )
            session.commit()

            result = get_overview(session, window="1h", tenant_id=None, assistant_id=None)

        self.assertEqual(2, result["kpis"]["total_calls"])
        self.assertEqual(1, result["kpis"]["success_calls"])
        self.assertEqual(1, result["kpis"]["handoff_calls"])


if __name__ == "__main__":
    unittest.main()
