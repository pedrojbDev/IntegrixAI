import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.ops.cost_sync_service import ParsedCallCost, VapiCostSyncService
from app.db import Base
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
    def test_parse_call_keeps_tenant_resolution_metadata(self) -> None:
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
                "startedAt": "2026-04-08T12:00:00Z",
                "endedAt": "2026-04-08T12:05:00Z",
                "assistantId": "asst_123",
                "status": "ended",
                "costTotalUsd": 1.23,
            }
        )

        self.assertIsNotNone(parsed)
        self.assertEqual("tenant_a", parsed.tenant_id)
        self.assertEqual("+5511999999999", parsed.to_number)

    def test_parse_call_does_not_assign_default_tenant_in_production(self) -> None:
        settings = production_settings()
        service = VapiCostSyncService(settings)

        parsed = service._parse_call(
            {
                "id": "call_123",
                "to": "+5511888888888",
                "startedAt": "2026-04-08T12:00:00Z",
                "endedAt": "2026-04-08T12:05:00Z",
                "assistantId": "asst_123",
                "status": "ended",
                "costTotalUsd": 1.23,
            }
        )

        self.assertIsNotNone(parsed)
        self.assertEqual("unknown", parsed.tenant_id)
        self.assertEqual("+5511888888888", parsed.to_number)

    def test_upsert_cost_batch_fallback_creates_and_updates_rows(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        settings = Settings(_env_file=None)
        service = VapiCostSyncService(settings)
        synced_at = datetime.now(timezone.utc)

        with session_local() as session:
            created, updated = service._upsert_cost_batch(
                session,
                [
                    ParsedCallCost(
                        call_id="call_123",
                        tenant_id="tenant_a",
                        to_number="+5511999999999",
                        started_at=synced_at,
                        ended_at=None,
                        duration_seconds=60.0,
                        assistant_id="asst_1",
                        status="ended",
                        cost_total_usd=1.0,
                        cost_breakdown_json={"total": 1.0},
                    )
                ],
                synced_at,
            )
            session.commit()

            created_again, updated_again = service._upsert_cost_batch(
                session,
                [
                    ParsedCallCost(
                        call_id="call_123",
                        tenant_id="tenant_a",
                        to_number="+5511999999999",
                        started_at=synced_at,
                        ended_at=None,
                        duration_seconds=120.0,
                        assistant_id="asst_1",
                        status="ended",
                        cost_total_usd=2.5,
                        cost_breakdown_json={"total": 2.5},
                    )
                ],
                synced_at,
            )
            session.commit()
            row = session.get(VapiCallCost, "call_123")

        self.assertEqual((1, 0), (created, updated))
        self.assertEqual((0, 1), (created_again, updated_again))
        self.assertIsNotNone(row)
        self.assertEqual(2.5, row.cost_total_usd)


if __name__ == "__main__":
    unittest.main()
