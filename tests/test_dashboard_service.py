import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.ops.dashboard_service import get_health, get_resilience
from app.db import Base
from app.models.call_event import CallEvent
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
            resilience = get_resilience(
                session,
                window="24h",
                tenant_id="tenant_a",
                assistant_id="asst_1",
            )

        self.assertEqual("critical", health["health_state"])
        self.assertEqual(1, health["counters"]["idempotency_hits"])
        self.assertEqual(1, health["counters"]["repeated_business_errors"])
        self.assertEqual("fresh", health["sync"]["freshness_state"])
        self.assertEqual(1, resilience["summary"]["idempotency_hits"])
        self.assertEqual(1, resilience["summary"]["repeated_business_errors"])
        self.assertTrue(resilience["series"]["failed_calls"])
        self.assertTrue(resilience["series"]["idempotency_hits"])
        self.assertTrue(resilience["series"]["repeated_business_errors"])
        self.assertEqual("search_providers", resilience["top_failure_tools"][0]["tool_name"])
        self.assertEqual("search_providers", resilience["business_error_tools"][0]["tool_name"])


if __name__ == "__main__":
    unittest.main()
