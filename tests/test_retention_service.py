from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.ops.retention_service import prune_operational_data
from app.db import Base
from app.models.call_event import CallEvent
from app.models.vapi_call_cost import VapiCallCost


class RetentionServiceTests(unittest.TestCase):
    def test_prune_operational_data_deletes_rows_older_than_retention(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        now = datetime.now(timezone.utc)
        settings = Settings(
            _env_file=None,
            db_enabled=True,
            call_events_retention_days=30,
            vapi_cost_retention_days=90,
        )

        with session_local() as session:
            session.add_all(
                [
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="old_event",
                        tool_name="handoff_human",
                        event_type="tool_completed",
                        payload_masked={},
                        created_at=now - timedelta(days=31),
                    ),
                    CallEvent(
                        tenant_id="tenant_a",
                        call_id="new_event",
                        tool_name="handoff_human",
                        event_type="tool_completed",
                        payload_masked={},
                        created_at=now - timedelta(days=1),
                    ),
                    VapiCallCost(
                        call_id="old_cost",
                        tenant_id="tenant_a",
                        synced_at=now - timedelta(days=91),
                    ),
                    VapiCallCost(
                        call_id="new_cost",
                        tenant_id="tenant_a",
                        synced_at=now - timedelta(days=1),
                    ),
                ]
            )
            session.commit()

            result = prune_operational_data(session, settings, now=now)
            event_count = session.execute(select(func.count(CallEvent.id))).scalar_one()
            cost_count = session.execute(select(func.count(VapiCallCost.call_id))).scalar_one()

        self.assertTrue(result["enabled"])
        self.assertEqual(1, result["call_events_deleted"])
        self.assertEqual(1, result["vapi_call_costs_deleted"])
        self.assertEqual(1, event_count)
        self.assertEqual(1, cost_count)


if __name__ == "__main__":
    unittest.main()
