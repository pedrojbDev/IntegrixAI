import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.ops import dashboard_costs
from app.config import Settings
from app.core.security.ops import OpsPrincipal
from app.db import Base


def cost_payload():
    return {
        "summary": {
            "total_cost_usd": 12.34,
            "total_cost_brl": 63.21,
            "avg_cost_per_call_usd": 1.23,
            "avg_cost_per_call_brl": 6.32,
        },
        "breakdown": [{"category": "llm", "cost_usd": 12.34}],
        "series": [{"cost_usd": 12.34, "cost_brl": 63.21}],
    }


class OpsCostVisibilityTests(unittest.TestCase):
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
            database_url="sqlite://",
            ops_cost_v2_enabled=False,
        )

    @staticmethod
    def principal(role: str) -> OpsPrincipal:
        return OpsPrincipal(
            id=role,
            email=f"{role}@example.com",
            role=role,
            tenant_ids=("tenant_a",) if role == "tenant_user" else (),
            must_change_password=False,
            session_token_hash="session",
            csrf_hash="csrf",
        )

    def test_client_values_are_redacted_until_release(self) -> None:
        with (
            patch("app.api.routes.ops.SessionLocal", self.session_local),
            patch("app.api.routes.ops.get_costs", return_value=cost_payload()),
        ):
            result = asyncio.run(
                dashboard_costs(
                    window="24h",
                    tenant_id="tenant_a",
                    assistant_id=None,
                    settings=self.settings,
                    principal=self.principal("tenant_user"),
                )
            )

        self.assertEqual("hidden", result["visibility"])
        self.assertEqual(0.0, result["summary"]["total_cost_usd"])
        self.assertIsNone(result["summary"]["total_cost_brl"])
        self.assertEqual([], result["breakdown"])

    def test_admin_can_preview_before_release(self) -> None:
        with (
            patch("app.api.routes.ops.SessionLocal", self.session_local),
            patch("app.api.routes.ops.get_costs", return_value=cost_payload()),
        ):
            result = asyncio.run(
                dashboard_costs(
                    window="24h",
                    tenant_id="tenant_a",
                    assistant_id=None,
                    settings=self.settings,
                    principal=self.principal("platform_admin"),
                )
            )

        self.assertEqual("admin_preview", result["visibility"])
        self.assertEqual(12.34, result["summary"]["total_cost_usd"])


if __name__ == "__main__":
    unittest.main()
